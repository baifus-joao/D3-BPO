from __future__ import annotations

import json
import re

import httpx

from webapp.dilmaria.config import get_settings
from webapp.dilmaria.exceptions import AgentExecutionError
from webapp.dilmaria.pop_context_refiner import PopContextRefinerService
from webapp.dilmaria.pop_prompt import POP_CONTENT_SYSTEM_PROMPT
from webapp.dilmaria.pop_schema import (
    GeneratedPopContent,
    GuidedPopRequest,
    PopDefinition,
    PopSubsection,
)
from webapp.dilmaria.pop_structures import get_pop_structure

COMMON_TERM_CORRECTIONS = {
    "aplicacao": "aplicação",
    "avaliacao": "avaliação",
    "boas praticas": "boas práticas",
    "biosseguranca": "biossegurança",
    "clinica": "clínica",
    "codigo": "código",
    "conclusao": "conclusão",
    "conformidade": "conformidade",
    "criterios": "critérios",
    "criticos": "críticos",
    "definicoes": "definições",
    "descricao": "descrição",
    "disponiveis": "disponíveis",
    "evidencias": "evidências",
    "execucao": "execução",
    "higienizacao": "higienização",
    "identificacao": "identificação",
    "mascara": "máscara",
    "nao": "não",
    "necessarios": "necessários",
    "objetivo": "objetivo",
    "oleo": "óleo",
    "observacao": "observação",
    "odontologica": "odontológica",
    "odontologico": "odontológico",
    "padrao": "padrão",
    "praticas": "práticas",
    "preparacao": "preparação",
    "protecao": "proteção",
    "referencia": "referência",
    "referencias": "referências",
    "responsavel": "responsável",
    "responsaveis": "responsáveis",
    "revisao": "revisão",
    "rotacao": "rotação",
    "saude": "saúde",
    "sequencia": "sequência",
    "sumario": "sumário",
    "tecnico": "técnico",
    "titulo": "título",
    "validacao": "validação",
    "lubrificacao": "lubrificação",
    "epi": "EPI",
}


class PopContentGeneratorService:
    async def build_content(self, request: GuidedPopRequest) -> GeneratedPopContent:
        content, _answers = await self.build_draft(request)
        return content

    async def build_draft(
        self, request: GuidedPopRequest
    ) -> tuple[GeneratedPopContent, dict[str, str]]:
        structure = get_pop_structure(request.structure_key)
        answers = await self.resolve_answers(request, structure)
        settings = get_settings()
        if settings.openai_api_key:
            content = await self._build_with_openai(request, structure, answers)
        else:
            content = self._build_with_fallback(request, structure, answers)
        return self._polish_generated_content(content), answers

    async def resolve_answers(self, request: GuidedPopRequest, structure) -> dict[str, str]:
        if request.creation_mode == "express":
            return await PopContextRefinerService().refine_answers(request, structure)
        answers = {key: value.strip() for key, value in request.answers.items() if isinstance(value, str)}
        missing_required = [
            question.label
            for question in structure.questions
            if question.required and not answers.get(question.id, "").strip()
        ]
        if missing_required:
            raise AgentExecutionError(
                "Respostas obrigatorias ausentes no modo avancado: "
                + ", ".join(missing_required)
            )
        return answers

    async def _build_with_openai(
        self,
        request: GuidedPopRequest,
        structure,
        answers: dict[str, str],
    ) -> GeneratedPopContent:
        settings = get_settings()
        answers_json = json.dumps(answers, ensure_ascii=False, indent=2)
        payload = {
            "model": settings.openai_model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": POP_CONTENT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Estrutura escolhida: {structure.name}\n"
                        f"Resumo: {structure.summary}\n"
                        f"Detalhes: {structure.details}\n"
                        f"Blueprint da secao 6: {json.dumps(structure.activity_blueprint, ensure_ascii=False)}\n"
                        f"Titulo do POP: {request.titulo}\n"
                        f"Codigo do POP: {request.codigo}\n"
                        f"Modo de criacao: {request.creation_mode}\n"
                        f"Respostas operacionais do usuario:\n{answers_json}"
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
            raise AgentExecutionError("Falha ao gerar o conteúdo do POP via IA.")

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return GeneratedPopContent.model_validate(parsed)

    def _build_with_fallback(
        self,
        request: GuidedPopRequest,
        structure,
        answers: dict[str, str],
    ) -> GeneratedPopContent:
        subsections: list[PopSubsection] = []
        step_descriptions = self._parse_lines(answers.get("fluxo_atividades", ""))
        materials = self._parse_lines(answers.get("materiais_recursos", ""))
        preparation = self._parse_lines(answers.get("preparacao_inicial", ""))
        references = self._parse_lines(answers.get("documentos_referencia", ""))
        criteria = self._parse_lines(answers.get("criterios_avaliacao", ""))
        good_practices = self._parse_lines(answers.get("boas_praticas", ""))
        critical_errors = self._parse_lines(answers.get("erros_criticos", ""))

        if not step_descriptions:
            raise AgentExecutionError("Informe o fluxo das atividades para gerar o conteúdo do POP.")

        grouped_steps = self._chunk_steps(step_descriptions, len(structure.activity_blueprint))
        for title, steps in zip(structure.activity_blueprint, grouped_steps):
            subsections.append(
                PopSubsection(
                    titulo=title,
                    materiais=materials if "Preparacao" in title or "Normas" in title else [],
                    preparacao=preparation if "Preparacao" in title or "Normas" in title else [],
                    etapas_iniciais=preparation[:2] if "Execucao" in title else [],
                    itens=[
                        {
                            "descricao": step,
                            "observacao": "Executar conforme o padrão definido e registrar desvios quando houver.",
                        }
                        for step in steps
                    ],
                )
            )

        definitions = []
        for line in self._parse_lines(answers.get("definicoes_siglas", "")):
            term, separator, description = line.partition(":")
            if separator and term.strip() and description.strip():
                definitions.append(PopDefinition(termo=term.strip(), descricao=description.strip()))

        context = answers.get("contexto_operacional", "").strip()
        responsibilities = answers.get("responsaveis_execucao", "").strip()
        location = answers.get("local_aplicacao", "").strip()

        return GeneratedPopContent(
            objetivo=(
                f"Padronizar {request.titulo.lower()} com base no contexto informado: {context}"
                if context
                else f"Padronizar {request.titulo.lower()}."
            ),
            documentos_referencia=references or ["Sem documentos de referência adicionais informados."],
            local_aplicacao=location or "Local de aplicação não informado.",
            responsabilidade_execucao=responsibilities or "Responsáveis pela execução não informados.",
            definicoes_siglas=definitions,
            atividades=subsections,
            criterios_avaliacao=criteria or ["Verificar a execução conforme o fluxo definido neste POP."],
            boas_praticas=good_practices or ["Manter registros atualizados e comunicar desvios imediatamente."],
            erros_criticos=critical_errors or ["Executar o processo fora da sequência definida neste POP."],
        )

    def _parse_lines(self, value: str) -> list[str]:
        return [item.strip() for item in value.splitlines() if item.strip()]

    def _chunk_steps(self, steps: list[str], chunk_count: int) -> list[list[str]]:
        if chunk_count <= 1:
            return [steps]
        buckets = [[] for _ in range(chunk_count)]
        for index, step in enumerate(steps):
            bucket_index = min(index * chunk_count // max(len(steps), 1), chunk_count - 1)
            buckets[bucket_index].append(step)
        return [bucket for bucket in buckets if bucket] or [steps]

    def _polish_generated_content(self, content: GeneratedPopContent) -> GeneratedPopContent:
        polished_definitions = [
            definition.model_copy(
                update={
                    "termo": self._normalize_fragment(definition.termo, lowercase_first=False),
                    "descricao": self._normalize_sentence(definition.descricao),
                }
            )
            for definition in content.definicoes_siglas
        ]
        polished_subsections = []
        for subsection in content.atividades:
            polished_subsections.append(
                subsection.model_copy(
                    update={
                        "titulo": self._normalize_fragment(subsection.titulo, lowercase_first=False),
                        "materiais": [self._normalize_list_entry(item) for item in subsection.materiais],
                        "preparacao": [self._normalize_list_entry(item) for item in subsection.preparacao],
                        "etapas_iniciais": [
                            self._normalize_list_entry(item) for item in subsection.etapas_iniciais
                        ],
                        "itens": [
                            item.model_copy(
                                update={
                                    "descricao": self._normalize_sentence(item.descricao),
                                    "observacao": self._normalize_sentence(item.observacao)
                                    if item.observacao
                                    else None,
                                }
                            )
                            for item in subsection.itens
                        ],
                    }
                )
            )

        return content.model_copy(
            update={
                "objetivo": self._normalize_sentence(content.objetivo),
                "documentos_referencia": [
                    self._normalize_reference(item) for item in content.documentos_referencia
                ],
                "local_aplicacao": self._normalize_location(content.local_aplicacao),
                "responsabilidade_execucao": self._normalize_responsibility(
                    content.responsabilidade_execucao
                ),
                "definicoes_siglas": polished_definitions,
                "atividades": polished_subsections,
                "criterios_avaliacao": [
                    self._normalize_sentence(item) for item in content.criterios_avaliacao
                ],
                "boas_praticas": [self._normalize_sentence(item) for item in content.boas_praticas],
                "erros_criticos": [self._normalize_sentence(item) for item in content.erros_criticos],
            }
        )

    def _normalize_location(self, value: str) -> str:
        cleaned = self._clean_text(value)
        if not cleaned:
            return "Local de aplicação não informado."
        if self._looks_like_sentence(cleaned):
            return self._normalize_sentence(cleaned)
        return self._normalize_sentence(f"Este procedimento se aplica ao seguinte local: {cleaned}")

    def _normalize_responsibility(self, value: str) -> str:
        cleaned = self._clean_text(value)
        if not cleaned:
            return "Os responsáveis pela execução deste procedimento não foram informados."
        if self._looks_like_sentence(cleaned):
            return self._normalize_sentence(cleaned)

        roles = self._split_compound_items(cleaned)
        if not roles:
            return self._normalize_sentence(cleaned)
        if len(roles) == 1:
            return self._normalize_sentence(
                f"A execução deste procedimento é de responsabilidade do seguinte profissional: {roles[0]}"
            )
        return self._normalize_sentence(
            "A execução deste procedimento é de responsabilidade dos seguintes profissionais: "
            + self._join_human_list(roles)
        )

    def _normalize_reference(self, value: str) -> str:
        return self._normalize_fragment(value, lowercase_first=False)

    def _normalize_list_entry(self, value: str) -> str:
        return self._normalize_sentence(value)

    def _normalize_sentence(self, value: str | None) -> str:
        cleaned = self._clean_text(value or "")
        if not cleaned:
            return ""
        normalized = self._capitalize_first_letter(cleaned)
        if normalized[-1] not in ".!?;:":
            normalized = f"{normalized}."
        return normalized

    def _normalize_fragment(self, value: str, lowercase_first: bool = False) -> str:
        cleaned = self._clean_text(value)
        if not cleaned:
            return ""
        normalized = self._capitalize_first_letter(cleaned)
        if lowercase_first and normalized:
            normalized = normalized[0].lower() + normalized[1:]
        return normalized.rstrip(" ;,")

    def _clean_text(self, value: str) -> str:
        collapsed = " ".join(str(value).split())
        return self._apply_term_corrections(collapsed)

    def _capitalize_first_letter(self, value: str) -> str:
        for index, character in enumerate(value):
            if character.isalpha():
                return value[:index] + character.upper() + value[index + 1 :]
        return value

    def _looks_like_sentence(self, value: str) -> bool:
        lowered = value.lower()
        verbal_markers = (
            " é ",
            " são ",
            " deve ",
            " devem ",
            " cabe ",
            " compete ",
            " executa ",
            " executam ",
            " aplica-se ",
            " aplica se ",
            " será ",
            " serão ",
        )
        return any(marker in f" {lowered} " for marker in verbal_markers) or value.endswith((".", "!", "?"))

    def _split_compound_items(self, value: str) -> list[str]:
        normalized_value = value.replace(";", ",").replace("\n", ",")
        raw_items = [item.strip(" .") for item in normalized_value.split(",") if item.strip(" .")]
        return [self._normalize_fragment(item, lowercase_first=True) for item in raw_items]

    def _join_human_list(self, items: list[str]) -> str:
        if len(items) == 1:
            return items[0]
        if len(items) == 2:
            return f"{items[0]} e {items[1]}"
        return f"{', '.join(items[:-1])} e {items[-1]}"

    def _apply_term_corrections(self, value: str) -> str:
        corrected = value
        for raw_term, replacement in COMMON_TERM_CORRECTIONS.items():
            pattern = re.compile(rf"\b{re.escape(raw_term)}\b", flags=re.IGNORECASE)
            corrected = pattern.sub(
                lambda match: self._match_replacement_case(match.group(0), replacement),
                corrected,
            )
        return corrected

    def _match_replacement_case(self, original: str, replacement: str) -> str:
        if original.isupper():
            return replacement.upper()
        if original[:1].isupper():
            return replacement[:1].upper() + replacement[1:]
        return replacement
