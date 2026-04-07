from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .bpo_models import BPOClient
from .finance_models import (
    BPOFinancialBankAccount,
    BPOFinancialCategory,
    BPOFinancialCostCenter,
    BPOFinancialPaymentMethod,
    BPOFinancialSupplier,
)


CLIENT_STATUS_LABELS = {
    "ativo": "Ativo",
    "implantacao": "Implantacao",
    "pausado": "Pausado",
    "inativo": "Inativo",
}

CATEGORY_KIND_LABELS = {
    "entrada": "Entrada",
    "saida": "Saida",
}


def _load_client_for_finance(db: Session, client_id: int) -> BPOClient:
    client = db.scalar(
        select(BPOClient)
        .where(BPOClient.id == client_id)
        .options(selectinload(BPOClient.responsible_user))
    )
    if not client:
        raise ValueError("Cliente financeiro nao encontrado.")
    if client.status == "inativo":
        raise ValueError("Cliente arquivado nao pode receber novos cadastros financeiros.")
    return client


def _serialize_finance_client(client: BPOClient) -> dict[str, object]:
    return {
        "id": client.id,
        "trade_name": client.trade_name or client.legal_name,
        "legal_name": client.legal_name,
        "document": client.document or "-",
        "segment": client.segment or "-",
        "status": client.status,
        "status_label": CLIENT_STATUS_LABELS.get(client.status, client.status.title()),
        "responsible_name": client.responsible_user.name if client.responsible_user else "Sem responsavel",
    }


def load_finance_setup_reference_lists(db: Session) -> dict[str, object]:
    clients = db.scalars(
        select(BPOClient)
        .options(selectinload(BPOClient.responsible_user))
        .order_by(BPOClient.trade_name.asc(), BPOClient.legal_name.asc())
    ).all()
    return {"finance_clients": [_serialize_finance_client(item) for item in clients]}


def load_finance_setup_overview(db: Session, *, client_id: int | None) -> dict[str, object]:
    if not client_id:
        return {
            "selected_finance_client": None,
            "finance_metrics": [],
            "bank_accounts": [],
            "category_rows": [],
            "cost_center_rows": [],
            "supplier_rows": [],
            "payment_method_rows": [],
        }

    client = db.scalar(
        select(BPOClient)
        .where(BPOClient.id == client_id)
        .options(selectinload(BPOClient.responsible_user))
    )
    if not client:
        return {
            "selected_finance_client": None,
            "finance_metrics": [],
            "bank_accounts": [],
            "category_rows": [],
            "cost_center_rows": [],
            "supplier_rows": [],
            "payment_method_rows": [],
        }

    bank_accounts = db.scalars(
        select(BPOFinancialBankAccount)
        .where(BPOFinancialBankAccount.client_id == client_id)
        .order_by(BPOFinancialBankAccount.account_name.asc(), BPOFinancialBankAccount.bank_name.asc())
    ).all()
    categories = db.scalars(
        select(BPOFinancialCategory)
        .where(BPOFinancialCategory.client_id == client_id)
        .order_by(BPOFinancialCategory.kind.asc(), BPOFinancialCategory.name.asc())
    ).all()
    cost_centers = db.scalars(
        select(BPOFinancialCostCenter)
        .where(BPOFinancialCostCenter.client_id == client_id)
        .order_by(BPOFinancialCostCenter.name.asc())
    ).all()
    suppliers = db.scalars(
        select(BPOFinancialSupplier)
        .where(BPOFinancialSupplier.client_id == client_id)
        .order_by(BPOFinancialSupplier.name.asc())
    ).all()
    payment_methods = db.scalars(
        select(BPOFinancialPaymentMethod)
        .where(BPOFinancialPaymentMethod.client_id == client_id)
        .order_by(BPOFinancialPaymentMethod.name.asc())
    ).all()

    category_names = {item.id: item.name for item in categories}

    return {
        "selected_finance_client": _serialize_finance_client(client),
        "finance_metrics": [
            {"label": "Contas bancarias", "value": len(bank_accounts)},
            {"label": "Categorias", "value": len(categories)},
            {"label": "Centros de custo", "value": len(cost_centers)},
            {"label": "Fornecedores", "value": len(suppliers)},
            {"label": "Formas de pagamento", "value": len(payment_methods)},
        ],
        "bank_accounts": [
            {
                "id": item.id,
                "account_name": item.account_name,
                "bank_name": item.bank_name,
                "agency": item.agency or "-",
                "account_number": item.account_number or "-",
                "pix_key": item.pix_key or "",
                "initial_balance": item.initial_balance,
                "is_active": item.is_active,
            }
            for item in bank_accounts
        ],
        "category_rows": [
            {
                "id": item.id,
                "name": item.name,
                "kind": item.kind,
                "kind_label": CATEGORY_KIND_LABELS.get(item.kind, item.kind.title()),
                "parent_name": category_names.get(item.parent_id, "-"),
                "is_active": item.is_active,
            }
            for item in categories
        ],
        "cost_center_rows": [
            {
                "id": item.id,
                "name": item.name,
                "is_active": item.is_active,
            }
            for item in cost_centers
        ],
        "supplier_rows": [
            {
                "id": item.id,
                "name": item.name,
                "document": item.document or "-",
                "email": item.email or "",
                "phone": item.phone or "",
                "is_active": item.is_active,
            }
            for item in suppliers
        ],
        "payment_method_rows": [
            {
                "id": item.id,
                "name": item.name,
                "is_active": item.is_active,
            }
            for item in payment_methods
        ],
    }


def create_financial_bank_account(
    db: Session,
    *,
    client_id: int,
    bank_name: str,
    account_name: str,
    agency: str,
    account_number: str,
    pix_key: str,
    initial_balance: Decimal,
) -> BPOFinancialBankAccount:
    _load_client_for_finance(db, client_id)
    existing = db.scalar(
        select(BPOFinancialBankAccount).where(
            BPOFinancialBankAccount.client_id == client_id,
            BPOFinancialBankAccount.account_name == account_name.strip(),
            BPOFinancialBankAccount.account_number == account_number.strip(),
        )
    )
    if existing:
        raise ValueError("Ja existe uma conta bancaria com esse nome e numero para o cliente.")
    item = BPOFinancialBankAccount(
        client_id=client_id,
        bank_name=bank_name.strip(),
        account_name=account_name.strip(),
        agency=agency.strip(),
        account_number=account_number.strip(),
        pix_key=pix_key.strip(),
        initial_balance=initial_balance,
        is_active=True,
    )
    db.add(item)
    db.commit()
    return item


def create_financial_category(
    db: Session,
    *,
    client_id: int,
    name: str,
    kind: str,
    parent_id: int | None,
) -> BPOFinancialCategory:
    _load_client_for_finance(db, client_id)
    normalized_kind = kind if kind in CATEGORY_KIND_LABELS else "saida"
    normalized_name = name.strip()
    existing = db.scalar(
        select(BPOFinancialCategory).where(
            BPOFinancialCategory.client_id == client_id,
            func.lower(BPOFinancialCategory.name) == normalized_name.lower(),
            BPOFinancialCategory.kind == normalized_kind,
        )
    )
    if existing:
        raise ValueError("Ja existe uma categoria com esse nome e tipo para o cliente.")
    if parent_id:
        parent = db.scalar(
            select(BPOFinancialCategory).where(
                BPOFinancialCategory.id == parent_id,
                BPOFinancialCategory.client_id == client_id,
            )
        )
        if not parent:
            raise ValueError("Categoria pai invalida para este cliente.")
    item = BPOFinancialCategory(
        client_id=client_id,
        name=normalized_name,
        kind=normalized_kind,
        parent_id=parent_id,
        is_active=True,
    )
    db.add(item)
    db.commit()
    return item


def create_financial_cost_center(
    db: Session,
    *,
    client_id: int,
    name: str,
) -> BPOFinancialCostCenter:
    _load_client_for_finance(db, client_id)
    normalized_name = name.strip()
    existing = db.scalar(
        select(BPOFinancialCostCenter).where(
            BPOFinancialCostCenter.client_id == client_id,
            func.lower(BPOFinancialCostCenter.name) == normalized_name.lower(),
        )
    )
    if existing:
        raise ValueError("Ja existe um centro de custo com esse nome para o cliente.")
    item = BPOFinancialCostCenter(client_id=client_id, name=normalized_name, is_active=True)
    db.add(item)
    db.commit()
    return item


def create_financial_supplier(
    db: Session,
    *,
    client_id: int,
    name: str,
    document: str,
    email: str,
    phone: str,
) -> BPOFinancialSupplier:
    _load_client_for_finance(db, client_id)
    normalized_name = name.strip()
    existing = db.scalar(
        select(BPOFinancialSupplier).where(
            BPOFinancialSupplier.client_id == client_id,
            func.lower(BPOFinancialSupplier.name) == normalized_name.lower(),
        )
    )
    if existing:
        raise ValueError("Ja existe um fornecedor com esse nome para o cliente.")
    item = BPOFinancialSupplier(
        client_id=client_id,
        name=normalized_name,
        document=document.strip(),
        email=email.strip(),
        phone=phone.strip(),
        is_active=True,
    )
    db.add(item)
    db.commit()
    return item


def create_financial_payment_method(
    db: Session,
    *,
    client_id: int,
    name: str,
) -> BPOFinancialPaymentMethod:
    _load_client_for_finance(db, client_id)
    normalized_name = name.strip()
    existing = db.scalar(
        select(BPOFinancialPaymentMethod).where(
            BPOFinancialPaymentMethod.client_id == client_id,
            func.lower(BPOFinancialPaymentMethod.name) == normalized_name.lower(),
        )
    )
    if existing:
        raise ValueError("Ja existe uma forma de pagamento com esse nome para o cliente.")
    item = BPOFinancialPaymentMethod(client_id=client_id, name=normalized_name, is_active=True)
    db.add(item)
    db.commit()
    return item
