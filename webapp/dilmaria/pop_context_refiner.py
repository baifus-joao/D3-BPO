from __future__ import annotations

import json
import re

import httpx

from webapp.dilmaria.config import get_settings
from webapp.dilmaria.exceptions import AgentExecutionError
from webapp.dilmaria.pop_prompt import POP_CONTEXT_REFINEMENT_SYSTEM_PROMPT
from webapp.dilmaria.pop_schema import GuidedPopRequest


class PopContextRefinerService:
    async def refine_answers(self, request: GuidedPopRequest, structure) -> dict[str, str]:
        settings = get_settings()
        if settings.openai_api_key:
            return await self._refine_with_openai(request, structure)
        return self._refine_with_fallback(request)

    async def _refine_with_openai(self, request: GuidedPopRequest, structure) -> dict[str, str]:
        settings = get_settings()
        questions = [
            {
                "id": question.id,
                "label": question.label,
                "help_text": question.help_text,
            }
            for question in structure.questions
        ]
        payload = {
            "model": settings.openai_model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": POP_CONTEXT_REFINEMENT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Estrutura escolhida: {structure.name}\n"
                        f"Resumo: {structure.summary}\n"
                        f"Detalhes: {structure.details}\n"
                        f"Blueprint da secao 6: {json.dumps(structure.activity_blueprint, ensure_ascii=False)}\n"
                        f"Perguntas esperadas: {json.dumps(questions, ensure_ascii=False)}\n"
                        f"Contexto em linguagem cotidiana:\n{request.raw_context}"
                    ),
                },
            ],
        }

        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                f"{settings.openai_base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )

        if response.status_code >= 400:
            raise AgentExecutionError("Falha ao refinar o contexto do POP via IA.")

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        answers = parsed.get("answers", {})
        if not isinstance(answers, dict):
            raise AgentExecutionError("A IA retornou um refinamento de contexto inválido.")
        return self._normalize_answers(answers)

    def _refine_with_fallback(self, request: GuidedPopRequest) -> dict[str, str]:
        context = (request.raw_context or "").strip()
        if not context:
            raise AgentExecutionError("Informe um contexto para usar o modo express.")

        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", context.replace("\n", " "))
            if sentence.strip()
        ]
        steps = self._derive_steps(sentences or [context])
        answers = {
            "contexto_operacional": context,
            "documentos_referencia": "",
            "local_aplicacao": "Conforme o ambiente operacional descrito no contexto informado.",
            "responsaveis_execucao": "Equipe responsável pela execução do processo descrito.",
            "definicoes_siglas": "",
            "materiais_recursos": "Definir materiais, insumos e sistemas necessários conforme o contexto operacional.",
            "preparacao_inicial": "Confirmar condições iniciais, recursos disponíveis e responsabilidades antes da execução.",
            "fluxo_atividades": "\n".join(steps),
            "criterios_avaliacao": "Execução concluída conforme o fluxo definido e sem desvios relevantes.",
            "boas_praticas": "Registrar evidências, manter o padrão operacional e comunicar não conformidades.",
            "erros_criticos": "Executar etapas fora da sequência ou sem validação prévia.",
        }
        return self._normalize_answers(answers)

    def _derive_steps(self, sentences: list[str]) -> list[str]:
        if len(sentences) == 1:
            base = sentences[0].rstrip(".")
            return [
                f"Preparar o ambiente e os recursos necessários para {base.lower()}",
                f"Executar o processo principal conforme o contexto descrito: {base}",
                "Registrar a conclusão do procedimento e tratar os desvios identificados",
            ]
        return [sentence.rstrip(".") for sentence in sentences]

    def _normalize_answers(self, answers: dict[str, object]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for key, value in answers.items():
            if value is None:
                normalized[key] = ""
            elif isinstance(value, list):
                normalized[key] = "\n".join(str(item).strip() for item in value if str(item).strip())
            else:
                normalized[key] = str(value).strip()
        return self._polish_answers(normalized)

    def _polish_answers(self, answers: dict[str, str]) -> dict[str, str]:
        polished = dict(answers)
        for field in (
            "contexto_operacional",
            "local_aplicacao",
            "responsaveis_execucao",
            "criterios_avaliacao",
            "boas_praticas",
            "erros_criticos",
        ):
            if polished.get(field):
                polished[field] = self._normalize_sentence(polished[field])

        for field in ("fluxo_atividades", "materiais_recursos", "preparacao_inicial"):
            if polished.get(field):
                polished[field] = "\n".join(
                    self._normalize_sentence(line)
                    for line in polished[field].splitlines()
                    if line.strip()
                )

        if polished.get("documentos_referencia"):
            polished["documentos_referencia"] = "\n".join(
                self._normalize_fragment(line)
                for line in polished["documentos_referencia"].splitlines()
                if line.strip()
            )
        if polished.get("definicoes_siglas"):
            polished["definicoes_siglas"] = "\n".join(
                self._normalize_fragment(line)
                for line in polished["definicoes_siglas"].splitlines()
                if line.strip()
            )
        return polished

    def _normalize_sentence(self, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            return ""
        normalized = cleaned[0].upper() + cleaned[1:]
        if normalized[-1] not in ".!?;:":
            normalized = f"{normalized}."
        return normalized

    def _normalize_fragment(self, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            return ""
        return cleaned[0].upper() + cleaned[1:]
