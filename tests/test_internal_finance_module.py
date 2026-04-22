from __future__ import annotations

import re

from sqlalchemy import select


def _extract_csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "csrf token não encontrado"
    return match.group(1)


def test_internal_finance_page_renders_reports(authenticated_client) -> None:
    response = authenticated_client.get("/gestao/contas")

    assert response.status_code == 200
    assert "Contas a pagar" in response.text
    assert "Contas a receber" in response.text
    assert "Novo lançamento" in response.text


def test_internal_finance_legacy_route_redirects_to_accounts(authenticated_client) -> None:
    response = authenticated_client.get("/gestao/financeiro", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/gestao/contas"


def test_internal_finance_form_page_renders_fields(authenticated_client) -> None:
    response = authenticated_client.get("/gestao/financeiro/novo")

    assert response.status_code == 200
    assert "Conta a pagar" in response.text
    assert "Conta a receber" in response.text
    assert "Interessado" in response.text
    assert "Parcelado" in response.text
    assert "Projeção" in response.text


def test_internal_finance_categories_are_seeded(client) -> None:
    from webapp.db import SessionLocal
    from webapp.models import FinancialCategory

    with SessionLocal() as db:
        categories = db.scalars(
            select(FinancialCategory.name).order_by(FinancialCategory.name.asc())
        ).all()

    assert "Operacional" in categories
    assert "Vendas" in categories
    assert any("Transfer" in item and "Sa" in item for item in categories)
    assert any("Transfer" in item and "Entrada" in item for item in categories)


def test_creates_installment_group_for_internal_finance(authenticated_client) -> None:
    from webapp.db import SessionLocal
    from webapp.models import FinancialCategory, FinancialTransaction

    form_page = authenticated_client.get("/gestao/financeiro/novo")
    csrf_token = _extract_csrf(form_page.text)

    with SessionLocal() as db:
        category_id = db.scalar(
            select(FinancialCategory.id).where(FinancialCategory.name == "Operacional")
        )
    assert category_id is not None

    response = authenticated_client.post(
        "/gestao/financeiro/lancamentos",
        data={
            "csrf_token": csrf_token,
            "type": "SAIDA",
            "entry_mode": "parcelado",
            "transaction_date": "2026-04-10",
            "description": "Aluguel sede",
            "interested_party": "Imobiliaria Central",
            "category_id": str(category_id),
            "subcategory": "Aluguel",
            "amount": "R$ 900,00",
            "status": "previsto",
            "installment_count": "3",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/gestao/contas"

    with SessionLocal() as db:
        rows = db.scalars(
            select(FinancialTransaction)
            .where(FinancialTransaction.description == "Aluguel sede")
            .order_by(FinancialTransaction.transaction_date.asc(), FinancialTransaction.id.asc())
        ).all()

    assert len(rows) == 3
    assert all(row.entry_mode == "parcelado" for row in rows)
    assert rows[0].group_key
    assert rows[0].installment_total == 3


def test_creates_projection_group_for_internal_finance(authenticated_client) -> None:
    from webapp.db import SessionLocal
    from webapp.models import FinancialCategory, FinancialTransaction

    form_page = authenticated_client.get("/gestao/financeiro/novo")
    csrf_token = _extract_csrf(form_page.text)

    with SessionLocal() as db:
        category_id = db.scalar(
            select(FinancialCategory.id).where(FinancialCategory.name == "Operacional")
        )
    assert category_id is not None

    response = authenticated_client.post(
        "/gestao/financeiro/lancamentos",
        data={
            "csrf_token": csrf_token,
            "type": "SAIDA",
            "entry_mode": "projecao",
            "transaction_date": "2026-05-05",
            "description": "Energia escritorio",
            "interested_party": "Concessionaria",
            "category_id": str(category_id),
            "subcategory": "Energia elétrica",
            "amount": "R$ 250,00",
            "status": "previsto",
            "projection_start": "2026-05-05",
            "projection_end": "2026-07-05",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303

    with SessionLocal() as db:
        rows = db.scalars(
            select(FinancialTransaction)
            .where(FinancialTransaction.description == "Energia escritorio")
            .order_by(FinancialTransaction.transaction_date.asc(), FinancialTransaction.id.asc())
        ).all()

    assert len(rows) == 3
    assert all(row.entry_mode == "projecao" for row in rows)
    assert rows[0].projection_start.isoformat() == "2026-05-05"
    assert rows[0].projection_end.isoformat() == "2026-07-05"

    projections_page = authenticated_client.get("/gestao/projecoes")

    assert projections_page.status_code == 200
    assert "Projeções" in projections_page.text
    assert "Energia escritorio" in projections_page.text


def test_duplicate_page_prefills_internal_finance_form(authenticated_client) -> None:
    from webapp.db import SessionLocal
    from webapp.models import FinancialCategory, FinancialTransaction

    form_page = authenticated_client.get("/gestao/financeiro/novo")
    csrf_token = _extract_csrf(form_page.text)

    with SessionLocal() as db:
        category_id = db.scalar(
            select(FinancialCategory.id).where(FinancialCategory.name == "Vendas")
        )
    assert category_id is not None

    authenticated_client.post(
        "/gestao/financeiro/lancamentos",
        data={
            "csrf_token": csrf_token,
            "type": "ENTRADA",
            "entry_mode": "avista",
            "transaction_date": "2026-04-15",
            "description": "Projeto especial",
            "interested_party": "Cliente interno",
            "category_id": str(category_id),
            "subcategory": "Projetos",
            "amount": "R$ 1200,00",
            "status": "realizado",
        },
        follow_redirects=False,
    )

    with SessionLocal() as db:
        item_id = db.scalar(
            select(FinancialTransaction.id).where(FinancialTransaction.description == "Projeto especial")
        )
    assert item_id is not None

    response = authenticated_client.get(f"/gestao/financeiro/novo?duplicate_id={item_id}")

    assert response.status_code == 200
    assert "Duplicando o lançamento" in response.text
    assert "Projeto especial" in response.text
    assert "Cliente interno" in response.text


def test_internal_finance_detail_page_renders_related_rows(authenticated_client) -> None:
    from webapp.db import SessionLocal
    from webapp.models import FinancialCategory, FinancialTransaction

    form_page = authenticated_client.get("/gestao/financeiro/novo")
    csrf_token = _extract_csrf(form_page.text)

    with SessionLocal() as db:
        category_id = db.scalar(
            select(FinancialCategory.id).where(FinancialCategory.name == "Operacional")
        )
    assert category_id is not None

    authenticated_client.post(
        "/gestao/financeiro/lancamentos",
        data={
            "csrf_token": csrf_token,
            "type": "SAIDA",
            "entry_mode": "parcelado",
            "transaction_date": "2026-06-20",
            "description": "Consultoria mensal",
            "interested_party": "Parceiro",
            "category_id": str(category_id),
            "subcategory": "Consultorias",
            "amount": "R$ 600,00",
            "status": "previsto",
            "installment_count": "2",
        },
        follow_redirects=False,
    )

    with SessionLocal() as db:
        item_id = db.scalar(
            select(FinancialTransaction.id).where(FinancialTransaction.description == "Consultoria mensal")
        )
    assert item_id is not None

    response = authenticated_client.get(f"/gestao/financeiro/lancamentos/{item_id}")

    assert response.status_code == 200
    assert "Itens vinculados" in response.text
    assert "Consultoria mensal" in response.text


def test_internal_entries_page_renders_operational_listing(authenticated_client) -> None:
    response = authenticated_client.get("/gestao/lancamentos")

    assert response.status_code == 200
    assert "Lista de registros" in response.text
    assert "Lançamentos" in response.text
