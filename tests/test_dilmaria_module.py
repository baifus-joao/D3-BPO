from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from webapp.dilmaria.pop_schema import PopRequest
from webapp.dilmaria.pop_service import _build_document, _build_pop


def build_guided_payload() -> dict:
    return {
        "creation_mode": "express",
        "structure_key": "operacional_padrao",
        "titulo": "POP de Atendimento Inicial",
        "codigo": "PO-ATEND-001",
        "data": "2026-04-06",
        "raw_context": (
            "Quando o cliente chega, a recepcao confirma o cadastro, direciona para a sala "
            "e informa a equipe sobre a chegada. Depois, tudo fica registrado no sistema."
        ),
        "answers": {},
        "termo": {
            "nome_responsavel": "Paula Pereira",
            "declaracao": (
                "Declaro que li, compreendi e me responsabilizo pelo cumprimento integral "
                "deste Procedimento Operacional Padrao."
            ),
            "elaborado_por": "Paula Pereira",
            "aprovado_por": "Carlos Souza",
            "local": "Sao Paulo",
            "data": "2026-04-06",
        },
    }


def test_dilmaria_page_preview_run_and_history(authenticated_client: TestClient) -> None:
    page = authenticated_client.get("/operacoes/dilmaria")
    assert page.status_code == 200
    assert "DilmarIA" in page.text
    assert "OPENAI_API_KEY" in page.text

    preview = authenticated_client.post(
        "/operacoes/dilmaria/api/preview",
        json=build_guided_payload(),
    )
    assert preview.status_code == 200
    preview_payload = preview.json()
    assert preview_payload["draft"]["titulo"] == "POP de Atendimento Inicial"
    assert preview_payload["structure_key"] == "operacional_padrao"

    exported = authenticated_client.post(
        "/operacoes/dilmaria/api/run",
        json=preview_payload["draft"],
    )
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert exported.headers["X-POP-Code"] == "PO-ATEND-001"
    assert exported.content[:2] == b"PK"

    history = authenticated_client.get("/operacoes/dilmaria/api/history?limit=8")
    assert history.status_code == 200
    history_payload = history.json()
    assert history_payload["total_execucoes"] == 1
    assert history_payload["recentes"][0]["codigo"] == "PO-ATEND-001"


def test_dilmaria_draft_save_restore_and_clear(authenticated_client: TestClient) -> None:
    preview = authenticated_client.post(
        "/operacoes/dilmaria/api/preview",
        json=build_guided_payload(),
    )
    assert preview.status_code == 200
    preview_payload = preview.json()

    draft_state = {
        "structure_key": "operacional_padrao",
        "creation_mode": "express",
        "custom_logo_name": None,
        "form_payload": build_guided_payload(),
        "preview": preview_payload,
    }

    saved = authenticated_client.post(
        "/operacoes/dilmaria/api/draft",
        json=draft_state,
    )
    assert saved.status_code == 200
    saved_payload = saved.json()
    assert saved_payload["codigo"] == "PO-ATEND-001"
    assert saved_payload["state"]["form_payload"]["titulo"] == "POP de Atendimento Inicial"

    loaded = authenticated_client.get("/operacoes/dilmaria/api/draft")
    assert loaded.status_code == 200
    loaded_payload = loaded.json()
    assert loaded_payload["draft"]["state"]["preview"]["draft"]["codigo"] == "PO-ATEND-001"

    cleared = authenticated_client.delete(
        "/operacoes/dilmaria/api/draft",
    )
    assert cleared.status_code == 200
    assert cleared.json()["cleared"] is True

    after_clear = authenticated_client.get("/operacoes/dilmaria/api/draft")
    assert after_clear.status_code == 200
    assert after_clear.json()["draft"] is None


def test_dilmaria_run_clears_saved_draft(authenticated_client: TestClient) -> None:
    preview = authenticated_client.post(
        "/operacoes/dilmaria/api/preview",
        json=build_guided_payload(),
    )
    preview_payload = preview.json()

    authenticated_client.post(
        "/operacoes/dilmaria/api/draft",
        json={
            "structure_key": "operacional_padrao",
            "creation_mode": "express",
            "custom_logo_name": None,
            "form_payload": build_guided_payload(),
            "preview": preview_payload,
        },
    )

    exported = authenticated_client.post(
        "/operacoes/dilmaria/api/run",
        json=preview_payload["draft"],
    )
    assert exported.status_code == 200

    loaded = authenticated_client.get("/operacoes/dilmaria/api/draft")
    assert loaded.status_code == 200
    assert loaded.json()["draft"] is None


def test_naturale_document_keeps_observation_after_activity_step() -> None:
    request = PopRequest.model_validate(
        {
            "structure_key": "pop_naturale",
            "titulo": "Procedimento de Teste Naturale",
            "codigo": "PO-TEST-001",
            "data": date(2026, 4, 6),
            "objetivo": "Garantir a ordem correta dos elementos no documento.",
            "documentos_referencia": ["Manual interno"],
            "local_aplicacao": "Clinica teste",
            "responsabilidade_execucao": "Equipe operacional",
            "definicoes_siglas": [{"termo": "POP", "descricao": "Procedimento Operacional Padrao"}],
            "atividades": [
                {
                    "titulo": "Execucao",
                    "itens": [
                        {
                            "descricao": "Executar o passo principal do procedimento.",
                            "observacao": "Registrar a evidencia logo apos a execucao.",
                        }
                    ],
                }
            ],
            "criterios_avaliacao": ["Passo registrado corretamente."],
            "boas_praticas": ["Seguir o fluxo definido."],
            "erros_criticos": ["Pular o registro da evidencia."],
            "termo": {
                "nome_responsavel": "Paula Pereira",
                "declaracao": "Declaro que li e compreendi o procedimento.",
                "elaborado_por": "Paula Pereira",
                "aprovado_por": "Carlos Souza",
                "local": "Sao Paulo",
                "data": date(2026, 4, 6),
            },
        }
    )

    pop = _build_pop(request, "Rev.01", "pop_naturale", "POP Naturale")
    document = _build_document(pop)
    paragraph_texts = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]

    step_index = paragraph_texts.index("6.1.1 Executar o passo principal do procedimento.")
    observation_index = paragraph_texts.index("Observação: Registrar a evidencia logo apos a execucao.")

    assert observation_index == step_index + 1


def test_naturale_document_applies_heading_hierarchy() -> None:
    request = PopRequest.model_validate(
        {
            "structure_key": "pop_naturale",
            "titulo": "Procedimento de Teste Naturale",
            "codigo": "PO-TEST-002",
            "data": date(2026, 4, 6),
            "objetivo": "Garantir destaque coerente para titulos e subtitulos.",
            "documentos_referencia": ["Manual interno"],
            "local_aplicacao": "Clinica teste",
            "responsabilidade_execucao": "Equipe operacional",
            "definicoes_siglas": [{"termo": "POP", "descricao": "Procedimento Operacional Padrao"}],
            "atividades": [
                {
                    "titulo": "Execucao",
                    "materiais": ["Checklist"],
                    "preparacao": ["Preparar o ambiente."],
                    "etapas_iniciais": ["Validar materiais."],
                    "itens": [{"descricao": "Executar o passo principal do procedimento."}],
                }
            ],
            "criterios_avaliacao": ["Passo registrado corretamente."],
            "boas_praticas": ["Seguir o fluxo definido."],
            "erros_criticos": ["Pular o registro da evidencia."],
            "termo": {
                "nome_responsavel": "Paula Pereira",
                "declaracao": "Declaro que li e compreendi o procedimento.",
                "elaborado_por": "Paula Pereira",
                "aprovado_por": "Carlos Souza",
                "local": "Sao Paulo",
                "data": date(2026, 4, 6),
            },
        }
    )

    pop = _build_pop(request, "Rev.01", "pop_naturale", "POP Naturale")
    document = _build_document(pop)

    paragraphs = {paragraph.text.strip(): paragraph for paragraph in document.paragraphs if paragraph.text.strip()}

    section = paragraphs["1. Objetivo"]
    subsection = paragraphs["6.1 Execucao"]
    label = paragraphs["Materiais Necessários"]

    assert section.runs[0].bold is True
    assert int(section.runs[0].font.size.pt) == 15
    assert subsection.runs[0].bold is True
    assert int(subsection.runs[0].font.size.pt) == 13
    assert label.runs[0].bold is True
    assert int(label.runs[0].font.size.pt) == 11
