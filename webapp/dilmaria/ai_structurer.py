from __future__ import annotations

import json
import re

import httpx

from webapp.dilmaria.config import get_settings
from webapp.dilmaria.doc_formatter_prompt import DOC_FORMATTER_SYSTEM_PROMPT
from webapp.dilmaria.doc_formatter_schema import StructuredBlock
from webapp.dilmaria.exceptions import AgentExecutionError


class AIStructurerService:
    async def structure_text(self, text: str) -> list[StructuredBlock]:
        settings = get_settings()
        if settings.openai_api_key:
            return await self._structure_with_openai(text)
        return self._structure_with_fallback(text)

    async def _structure_with_openai(self, text: str) -> list[StructuredBlock]:
        settings = get_settings()
        payload = {
            "model": settings.openai_model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": DOC_FORMATTER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Estruture o texto abaixo exatamente no schema solicitado.\n\n"
                        f"TEXTO:\n{text}"
                    ),
                },
            ],
        }

        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{settings.openai_base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )

        if response.status_code >= 400:
            raise AgentExecutionError("Falha ao estruturar texto via IA.")

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        blocks = parsed.get("blocks", parsed)
        return self._validate_blocks(blocks)

    def _structure_with_fallback(self, text: str) -> list[StructuredBlock]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            raise AgentExecutionError("Nao foi possivel estruturar um texto vazio.")

        blocks: list[dict[str, str]] = []
        for line in lines:
            if self._looks_like_title(line):
                block_type = "title"
            elif self._looks_like_subtitle(line):
                block_type = "subtitle"
            else:
                block_type = "paragraph"
            blocks.append({"type": block_type, "content": line})

        return self._validate_blocks(blocks)

    def _looks_like_title(self, line: str) -> bool:
        normalized = line.strip()
        if len(normalized) > 100:
            return False
        if normalized.endswith((".", "!", "?", ";", ":")):
            return False
        letters = [char for char in normalized if char.isalpha()]
        if not letters:
            return False
        return "".join(letters).isupper()

    def _looks_like_subtitle(self, line: str) -> bool:
        if len(line) <= 80 and line.endswith(":"):
            return True
        if re.match(r"^\d+(\.\d+)*\s+\S+", line):
            return True
        return False

    def _validate_blocks(self, blocks: object) -> list[StructuredBlock]:
        if not isinstance(blocks, list):
            raise AgentExecutionError("A IA retornou um formato de blocos invalido.")

        try:
            return [StructuredBlock.model_validate(block) for block in blocks]
        except Exception as exc:
            raise AgentExecutionError("A IA retornou blocos incompatíveis com o schema.") from exc
