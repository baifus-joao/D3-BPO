from __future__ import annotations

import re

from sqlalchemy import select


def _extract_csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "csrf token não encontrado"
    return match.group(1)


def test_operations_pages_render_task_manager_structure(authenticated_client) -> None:
    dashboard = authenticated_client.get("/operacoes/dashboard")
    assert dashboard.status_code == 200
    assert "Gestor de tarefas" in dashboard.text
    assert "Conciliação" in dashboard.text
    assert "DilmarIA" in dashboard.text

    routes = [
        ("/operacoes/gestor-tarefas", "Onde agir agora"),
        ("/operacoes/gestor-tarefas/clientes", "Base de clientes"),
        ("/operacoes/gestor-tarefas/projetos", "Projetos por cliente"),
        ("/operacoes/gestor-tarefas/tarefas", "Tarefas operacionais"),
        ("/operacoes/gestor-tarefas/demandas", "Demandas de entrada"),
        ("/operacoes/gestor-tarefas/tempo", "Apontamentos em andamento"),
        ("/operacoes/gestor-tarefas/rotinas", "Rotinas automáticas"),
        ("/operacoes/gestor-tarefas/alertas", "Pontos de atenção"),
        ("/operacoes/gestor-tarefas/performance", "Performance por colaborador"),
    ]

    for route, marker in routes:
        response = authenticated_client.get(route)
        assert response.status_code == 200
        assert marker in response.text


def test_creates_project_and_converts_demand_to_task(authenticated_client) -> None:
    from webapp.bpo_models import BPOClient, BPODemand, BPOProject
    from webapp.db import SessionLocal

    page = authenticated_client.get("/operacoes/gestor-tarefas/clientes")
    csrf = _extract_csrf(page.text)

    authenticated_client.post(
        "/operacoes/clientes",
        data={
            "csrf_token": csrf,
            "legal_name": "Cliente Operacional LTDA",
            "trade_name": "Cliente Operacional",
            "document": "00.000.000/0001-00",
            "segment": "BPO",
            "contracted_plan": "Mensal",
            "sla_deadline_day": "5",
            "team_label": "Squad Azul",
            "notes": "Cliente de teste",
        },
        follow_redirects=False,
    )

    with SessionLocal() as db:
        client_id = db.scalar(select(BPOClient.id).where(BPOClient.trade_name == "Cliente Operacional"))
    assert client_id is not None

    projects_page = authenticated_client.get("/operacoes/gestor-tarefas/projetos")
    csrf = _extract_csrf(projects_page.text)
    authenticated_client.post(
        "/operacoes/gestor-tarefas/projetos",
        data={
            "csrf_token": csrf,
            "client_id": str(client_id),
            "name": "Rotina abril",
            "project_type": "rotina_mensal",
            "status": "ativo",
        },
        follow_redirects=False,
    )

    with SessionLocal() as db:
        project_id = db.scalar(select(BPOProject.id).where(BPOProject.name == "Rotina abril"))
    assert project_id is not None

    demands_page = authenticated_client.get("/operacoes/gestor-tarefas/demandas")
    csrf = _extract_csrf(demands_page.text)
    authenticated_client.post(
        "/operacoes/gestor-tarefas/demandas",
        data={
            "csrf_token": csrf,
            "client_id": str(client_id),
            "project_id": str(project_id),
            "title": "Solicitação de relatório",
            "description": "Cliente pediu relatório mensal",
            "source": "email",
            "demand_type": "operacional",
            "priority": "alta",
            "status": "aberta",
        },
        follow_redirects=False,
    )

    with SessionLocal() as db:
        demand_id = db.scalar(select(BPODemand.id).where(BPODemand.title == "Solicitação de relatório"))
    assert demand_id is not None

    convert_page = authenticated_client.get("/operacoes/gestor-tarefas/demandas")
    csrf = _extract_csrf(convert_page.text)
    response = authenticated_client.post(
        f"/operacoes/gestor-tarefas/demandas/{demand_id}/converter",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert response.status_code == 303

    with SessionLocal() as db:
        demand = db.scalar(select(BPODemand).where(BPODemand.id == demand_id))
    assert demand is not None
    assert demand.converted_task_id is not None
    assert demand.status == "convertida"
