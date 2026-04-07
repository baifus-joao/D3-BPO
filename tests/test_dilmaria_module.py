from __future__ import annotations

from fastapi.testclient import TestClient


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
