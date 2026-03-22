from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass

try:
    from openai import OpenAI
    from openai import APIConnectionError, APIStatusError, RateLimitError
except Exception:  # pragma: no cover - dependencia opcional
    OpenAI = None
    APIConnectionError = Exception
    APIStatusError = Exception
    RateLimitError = Exception


SCHEMA_HINTS = {
    "vendas": {
        "comprovante": "codigo unico da venda, nsu ou comprovante",
        "parcelas": "texto do parcelamento, ex.: 1/3 ou 1 de 3",
        "data_venda": "data original da venda",
        "data_prevista_pagamento": "data prevista de pagamento ou liquidacao",
        "valor_bruto_parcela": "valor bruto da parcela",
        "valor_liquido_parcela": "valor liquido da parcela",
        "status_venda": "status da venda",
        "status_pagamento": "status do pagamento da venda",
    },
    "recebimentos": {
        "comprovante": "codigo unico da venda, nsu ou comprovante",
        "parcelas": "texto do parcelamento, ex.: 1/3 ou 1 de 3",
        "data_pagamento": "data em que a parcela foi paga/recebida",
        "codigo_pagamento": "codigo do pagamento, lote ou identificador do repasse",
        "bruto_parcela": "valor bruto da parcela recebida",
        "liquido_venda": "valor liquido recebido",
        "desconto_mdr": "desconto, taxa ou mdr",
        "tipo_pagamento": "tipo do pagamento",
    },
}

REQUIRED_FIELDS = {
    "vendas": ["comprovante", "parcelas", "data_venda", "valor_bruto_parcela"],
    "recebimentos": ["comprovante", "parcelas", "data_pagamento", "bruto_parcela"],
}


def normalize_text(value):
    text = str(value).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text)


@dataclass
class InferredLayout:
    report_type: str
    header_row_index: int
    confidence: float
    mapped_columns: dict[str, str]
    missing_columns: list[str]
    notes: list[str]


class AILayoutInferenceError(RuntimeError):
    pass


def is_ai_layout_enabled() -> bool:
    return OpenAI is not None and bool(os.getenv("OPENAI_API_KEY"))


def _get_client() -> OpenAI | None:
    if not is_ai_layout_enabled():
        return None
    return OpenAI()


def _trim_row(values):
    trimmed = list(values)
    while trimmed and normalize_text(trimmed[-1]) in {"", "nan", "none"}:
        trimmed.pop()
    return [str(value) for value in trimmed]


def build_sheet_preview(raw_df, max_rows=30, max_cols=20):
    preview = []
    for idx in range(min(len(raw_df), max_rows)):
        row = raw_df.iloc[idx].tolist()[:max_cols]
        values = _trim_row(row)
        if not values:
            continue
        preview.append({"row_index": idx, "values": values})
    return preview


def _resolve_header_name(header_values, inferred_name):
    inferred_normalized = normalize_text(inferred_name)
    if not inferred_normalized:
        return None

    mapping = {normalize_text(value): value for value in header_values}
    if inferred_normalized in mapping:
        return mapping[inferred_normalized]

    for normalized, original in mapping.items():
        if inferred_normalized in normalized or normalized in inferred_normalized:
            return original
    return None


def validate_inferred_layout(raw_df, inferred_data, expected_type=None):
    report_type = str(inferred_data.get("report_type", "")).strip().lower()
    if expected_type and report_type != expected_type:
        return None
    if report_type not in SCHEMA_HINTS:
        return None

    try:
        header_row_index = int(inferred_data.get("header_row_index"))
    except Exception:
        return None
    if header_row_index < 0 or header_row_index >= len(raw_df):
        return None

    header_values = [str(value) for value in raw_df.iloc[header_row_index].tolist()]
    resolved_columns = {}
    for target_name, inferred_name in dict(inferred_data.get("mapped_columns", {})).items():
        resolved = _resolve_header_name(header_values, inferred_name)
        if resolved:
            resolved_columns[target_name] = resolved

    required = REQUIRED_FIELDS[report_type]
    missing = [field for field in required if field not in resolved_columns]
    if missing:
        return None

    try:
        confidence = float(inferred_data.get("confidence", 0))
    except Exception:
        confidence = 0.0

    return InferredLayout(
        report_type=report_type,
        header_row_index=header_row_index,
        confidence=max(0.0, min(confidence, 1.0)),
        mapped_columns=resolved_columns,
        missing_columns=list(inferred_data.get("missing_columns", [])),
        notes=list(inferred_data.get("notes", [])),
    )


def infer_layout_with_ai(raw_df, filename, expected_type=None):
    client = _get_client()
    if client is None:
        return None

    preview = build_sheet_preview(raw_df)
    if not preview:
        return None

    scope = expected_type or "vendas ou recebimentos"
    schema_hints = SCHEMA_HINTS[expected_type] if expected_type else SCHEMA_HINTS

    prompt = {
        "task": "Inferir a estrutura de um relatorio Excel financeiro.",
        "filename": filename,
        "expected_type": scope,
        "supported_types": ["vendas", "recebimentos"],
        "canonical_schema": schema_hints,
        "required_fields": REQUIRED_FIELDS.get(expected_type, REQUIRED_FIELDS),
        "preview_rows": preview,
        "instructions": [
            "Responda apenas JSON valido.",
            "Escolha a linha do cabecalho real.",
            "Mapeie as colunas reais para as chaves canonicas.",
            "Se nao tiver confianca suficiente, use confidence menor que 0.75.",
            "Nao invente colunas ausentes.",
        ],
        "output_schema": {
            "report_type": "vendas ou recebimentos",
            "header_row_index": 0,
            "confidence": 0.0,
            "mapped_columns": {"campo_canonico": "nome exato da coluna"},
            "missing_columns": ["campo_canonico"],
            "notes": ["observacoes curtas"],
        },
    }

    try:
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_LAYOUT_MODEL", "gpt-4.1-mini"),
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Voce analisa planilhas financeiras e identifica o tipo de relatorio, a linha de cabecalho "
                        "e o mapeamento de colunas para um schema canonico. Sempre responda JSON valido."
                    ),
                },
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
        )
    except RateLimitError as exc:
        raise AILayoutInferenceError(
            "Falha ao consultar a OpenAI para inferir o layout: cota insuficiente ou limite excedido."
        ) from exc
    except APIConnectionError as exc:
        raise AILayoutInferenceError(
            "Falha ao consultar a OpenAI para inferir o layout: erro de conexao com a API."
        ) from exc
    except APIStatusError as exc:
        raise AILayoutInferenceError(
            f"Falha ao consultar a OpenAI para inferir o layout: API retornou status {exc.status_code}."
        ) from exc
    except Exception as exc:
        raise AILayoutInferenceError(
            "Falha inesperada ao consultar a OpenAI para inferir o layout."
        ) from exc

    content = response.choices[0].message.content or "{}"
    inferred_data = json.loads(content)
    return validate_inferred_layout(raw_df, inferred_data, expected_type=expected_type)
