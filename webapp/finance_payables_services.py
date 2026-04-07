from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .bpo_models import BPOClient
from .finance_models import (
    BPOFinancialBankAccount,
    BPOFinancialCategory,
    BPOFinancialCostCenter,
    BPOFinancialPayable,
    BPOFinancialPayableEvent,
    BPOFinancialPayablePayment,
    BPOFinancialPaymentMethod,
    BPOFinancialSupplier,
)
from .models import User


PAYABLE_STATUS_LABELS = {
    "aberto": "Aberto",
    "parcial": "Parcial",
    "pago": "Pago",
    "cancelado": "Cancelado",
}

PAYABLE_STATUS_CLASS = {
    "aberto": "neutral",
    "parcial": "warning",
    "pago": "success",
    "cancelado": "neutral",
}


def _money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _load_client_for_payables(db: Session, client_id: int) -> BPOClient:
    client = db.scalar(select(BPOClient).where(BPOClient.id == client_id))
    if not client:
        raise ValueError("Cliente nao encontrado para contas a pagar.")
    if client.status == "inativo":
        raise ValueError("Cliente arquivado nao pode receber novos titulos.")
    return client


def _require_client_reference(db: Session, model, *, item_id: int | None, client_id: int, label: str):
    if item_id is None:
        return None
    filters = [model.id == item_id, model.client_id == client_id]
    if hasattr(model, "is_active"):
        filters.append(model.is_active.is_(True))
    item = db.scalar(select(model).where(*filters))
    if not item:
        raise ValueError(f"{label} invalido para este cliente.")
    return item


def _load_payable_for_update(db: Session, payable_id: int) -> BPOFinancialPayable:
    payable = db.scalar(
        select(BPOFinancialPayable)
        .where(BPOFinancialPayable.id == payable_id)
        .options(
            selectinload(BPOFinancialPayable.payments),
            selectinload(BPOFinancialPayable.events),
            selectinload(BPOFinancialPayable.client),
            selectinload(BPOFinancialPayable.supplier),
            selectinload(BPOFinancialPayable.category),
            selectinload(BPOFinancialPayable.cost_center),
            selectinload(BPOFinancialPayable.payment_method),
            selectinload(BPOFinancialPayable.bank_account),
            selectinload(BPOFinancialPayable.assigned_user),
        )
    )
    if not payable:
        raise ValueError("Titulo a pagar nao encontrado.")
    return payable


def _require_assigned_user(db: Session, user_id: int | None) -> None:
    if user_id is None:
        return
    user = db.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    if not user:
        raise ValueError("Responsavel invalido para o titulo.")


def _register_event(db: Session, *, payable_id: int, user_id: int | None, event_type: str, description: str) -> None:
    db.add(
        BPOFinancialPayableEvent(
            payable_id=payable_id,
            user_id=user_id,
            event_type=event_type,
            description=description.strip(),
        )
    )


def _recalculate_payable_status(db: Session, payable: BPOFinancialPayable) -> None:
    paid_total = db.scalar(
        select(func.coalesce(func.sum(BPOFinancialPayablePayment.amount), 0)).where(
            BPOFinancialPayablePayment.payable_id == payable.id
        )
    )
    payable.paid_amount = _money(paid_total or 0)
    if payable.status == "cancelado":
        return
    if payable.paid_amount <= Decimal("0.00"):
        payable.status = "aberto"
    elif payable.paid_amount < _money(payable.amount):
        payable.status = "parcial"
    else:
        payable.status = "pago"


def _serialize_payable(payable: BPOFinancialPayable) -> dict[str, object]:
    amount = _money(payable.amount)
    paid_amount = _money(payable.paid_amount)
    remaining_amount = amount - paid_amount
    is_overdue = payable.status in {"aberto", "parcial"} and payable.due_date < date.today()
    return {
        "id": payable.id,
        "client_id": payable.client_id,
        "client_name": (payable.client.trade_name or payable.client.legal_name) if payable.client else "Cliente removido",
        "title": payable.title,
        "description": payable.description,
        "document_number": payable.document_number or "-",
        "supplier_name": payable.supplier.name if payable.supplier else "Sem fornecedor",
        "category_name": payable.category.name if payable.category else "Sem categoria",
        "cost_center_name": payable.cost_center.name if payable.cost_center else "Sem centro de custo",
        "payment_method_name": payable.payment_method.name if payable.payment_method else "Sem forma de pagamento",
        "bank_account_name": payable.bank_account.account_name if payable.bank_account else "Sem conta",
        "assigned_user_name": payable.assigned_user.name if payable.assigned_user else "Sem responsavel",
        "issue_date": payable.issue_date.strftime("%d/%m/%Y"),
        "issue_date_iso": payable.issue_date.isoformat(),
        "due_date": payable.due_date.strftime("%d/%m/%Y"),
        "due_date_iso": payable.due_date.isoformat(),
        "competence_date": payable.competence_date.strftime("%m/%Y") if payable.competence_date else "-",
        "competence_date_iso": payable.competence_date.isoformat() if payable.competence_date else "",
        "amount": amount,
        "paid_amount": paid_amount,
        "remaining_amount": remaining_amount,
        "status": payable.status,
        "status_label": PAYABLE_STATUS_LABELS.get(payable.status, payable.status.title()),
        "status_class": PAYABLE_STATUS_CLASS.get(payable.status, "neutral"),
        "notes": payable.notes,
        "is_overdue": is_overdue,
        "can_edit": payable.status in {"aberto", "parcial"},
        "can_cancel": payable.status in {"aberto", "parcial"},
        "can_reactivate": payable.status == "cancelado",
        "can_register_payment": payable.status in {"aberto", "parcial"},
        "payments": [
            {
                "id": item.id,
                "payment_date": item.payment_date.strftime("%d/%m/%Y"),
                "amount": _money(item.amount),
                "reference": item.reference or "-",
                "bank_account_name": item.bank_account.account_name if item.bank_account else "Sem conta",
                "created_by_name": item.created_by.name if item.created_by else "Sistema",
            }
            for item in sorted(payable.payments, key=lambda row: (row.payment_date, row.created_at), reverse=True)
        ],
        "events": [
            {
                "id": item.id,
                "event_type": item.event_type,
                "description": item.description,
                "created_at": item.created_at.strftime("%d/%m/%Y %H:%M"),
                "user_name": item.user.name if item.user else "Sistema",
            }
            for item in sorted(payable.events, key=lambda row: row.created_at, reverse=True)
        ],
    }


def load_payables_reference_lists(db: Session, *, client_id: int | None = None) -> dict[str, object]:
    clients = db.scalars(select(BPOClient).order_by(BPOClient.trade_name.asc(), BPOClient.legal_name.asc())).all()
    selected_client_id = client_id
    if selected_client_id is None and clients:
        active = next((item for item in clients if item.status != "inativo"), None)
        selected_client_id = (active or clients[0]).id

    if not selected_client_id:
        return {
            "payable_clients": clients,
            "payable_suppliers": [],
            "payable_categories": [],
            "payable_cost_centers": [],
            "payable_payment_methods": [],
            "payable_bank_accounts": [],
        }

    return {
        "payable_clients": clients,
        "payable_suppliers": db.scalars(
            select(BPOFinancialSupplier)
            .where(BPOFinancialSupplier.client_id == selected_client_id, BPOFinancialSupplier.is_active.is_(True))
            .order_by(BPOFinancialSupplier.name.asc())
        ).all(),
        "payable_categories": db.scalars(
            select(BPOFinancialCategory)
            .where(BPOFinancialCategory.client_id == selected_client_id, BPOFinancialCategory.is_active.is_(True))
            .order_by(BPOFinancialCategory.kind.asc(), BPOFinancialCategory.name.asc())
        ).all(),
        "payable_cost_centers": db.scalars(
            select(BPOFinancialCostCenter)
            .where(BPOFinancialCostCenter.client_id == selected_client_id, BPOFinancialCostCenter.is_active.is_(True))
            .order_by(BPOFinancialCostCenter.name.asc())
        ).all(),
        "payable_payment_methods": db.scalars(
            select(BPOFinancialPaymentMethod)
            .where(BPOFinancialPaymentMethod.client_id == selected_client_id, BPOFinancialPaymentMethod.is_active.is_(True))
            .order_by(BPOFinancialPaymentMethod.name.asc())
        ).all(),
        "payable_bank_accounts": db.scalars(
            select(BPOFinancialBankAccount)
            .where(BPOFinancialBankAccount.client_id == selected_client_id, BPOFinancialBankAccount.is_active.is_(True))
            .order_by(BPOFinancialBankAccount.account_name.asc())
        ).all(),
    }


def load_payables_overview(db: Session, *, filters: dict[str, object] | None = None) -> dict[str, object]:
    filters = filters or {}
    client_id = filters.get("client_id")
    status = str(filters.get("status") or "").strip()
    supplier_id = filters.get("supplier_id")
    assigned_user_id = filters.get("assigned_user_id")
    due_from = filters.get("due_from")
    due_to = filters.get("due_to")

    query = (
        select(BPOFinancialPayable)
        .options(
            selectinload(BPOFinancialPayable.client),
            selectinload(BPOFinancialPayable.supplier),
            selectinload(BPOFinancialPayable.category),
            selectinload(BPOFinancialPayable.cost_center),
            selectinload(BPOFinancialPayable.payment_method),
            selectinload(BPOFinancialPayable.bank_account),
            selectinload(BPOFinancialPayable.assigned_user),
            selectinload(BPOFinancialPayable.payments).selectinload(BPOFinancialPayablePayment.bank_account),
            selectinload(BPOFinancialPayable.payments).selectinload(BPOFinancialPayablePayment.created_by),
            selectinload(BPOFinancialPayable.events).selectinload(BPOFinancialPayableEvent.user),
        )
        .order_by(BPOFinancialPayable.due_date.asc(), BPOFinancialPayable.created_at.desc())
    )
    if client_id:
        query = query.where(BPOFinancialPayable.client_id == client_id)
    if status:
        query = query.where(BPOFinancialPayable.status == status)
    if supplier_id:
        query = query.where(BPOFinancialPayable.supplier_id == supplier_id)
    if assigned_user_id:
        query = query.where(BPOFinancialPayable.assigned_user_id == assigned_user_id)
    if due_from:
        query = query.where(BPOFinancialPayable.due_date >= due_from)
    if due_to:
        query = query.where(BPOFinancialPayable.due_date <= due_to)

    rows = db.scalars(query.limit(200)).all()
    serialized_rows = [_serialize_payable(item) for item in rows]

    open_titles = [item for item in serialized_rows if item["status"] == "aberto"]
    partial_titles = [item for item in serialized_rows if item["status"] == "parcial"]
    paid_titles = [item for item in serialized_rows if item["status"] == "pago"]
    overdue_titles = [item for item in serialized_rows if item["is_overdue"]]

    return {
        "payable_metrics": [
            {"label": "Titulos filtrados", "value": len(serialized_rows)},
            {"label": "Abertos", "value": len(open_titles)},
            {"label": "Parciais", "value": len(partial_titles)},
            {"label": "Vencidos", "value": len(overdue_titles)},
            {"label": "Pagos", "value": len(paid_titles)},
        ],
        "payable_rows": serialized_rows,
        "payable_filters": {
            "client_id": client_id,
            "status": status,
            "supplier_id": supplier_id,
            "assigned_user_id": assigned_user_id,
            "due_from": due_from.isoformat() if due_from else "",
            "due_to": due_to.isoformat() if due_to else "",
        },
    }


def create_payable(
    db: Session,
    *,
    client_id: int,
    title: str,
    description: str,
    document_number: str,
    issue_date: date,
    due_date: date,
    competence_date: date | None,
    amount: Decimal,
    supplier_id: int | None,
    category_id: int | None,
    cost_center_id: int | None,
    payment_method_id: int | None,
    bank_account_id: int | None,
    assigned_user_id: int | None,
    created_by_user_id: int | None,
    notes: str,
) -> BPOFinancialPayable:
    _load_client_for_payables(db, client_id)
    normalized_amount = _money(amount)
    if normalized_amount <= Decimal("0.00"):
        raise ValueError("O valor do titulo precisa ser maior que zero.")
    _require_client_reference(db, BPOFinancialSupplier, item_id=supplier_id, client_id=client_id, label="Fornecedor")
    _require_client_reference(db, BPOFinancialCategory, item_id=category_id, client_id=client_id, label="Categoria")
    _require_client_reference(db, BPOFinancialCostCenter, item_id=cost_center_id, client_id=client_id, label="Centro de custo")
    _require_client_reference(db, BPOFinancialPaymentMethod, item_id=payment_method_id, client_id=client_id, label="Forma de pagamento")
    _require_client_reference(db, BPOFinancialBankAccount, item_id=bank_account_id, client_id=client_id, label="Conta bancaria")
    _require_assigned_user(db, assigned_user_id)

    payable = BPOFinancialPayable(
        client_id=client_id,
        supplier_id=supplier_id,
        category_id=category_id,
        cost_center_id=cost_center_id,
        payment_method_id=payment_method_id,
        bank_account_id=bank_account_id,
        title=title.strip(),
        description=description.strip(),
        document_number=document_number.strip(),
        issue_date=issue_date,
        due_date=due_date,
        competence_date=competence_date,
        amount=normalized_amount,
        paid_amount=Decimal("0.00"),
        status="aberto",
        assigned_user_id=assigned_user_id,
        created_by_user_id=created_by_user_id,
        notes=notes.strip(),
    )
    db.add(payable)
    db.flush()
    _register_event(
        db,
        payable_id=payable.id,
        user_id=created_by_user_id,
        event_type="criado",
        description="Titulo a pagar criado no ERP financeiro do cliente.",
    )
    db.commit()
    return _load_payable_for_update(db, payable.id)


def update_payable(
    db: Session,
    *,
    payable_id: int,
    title: str,
    description: str,
    document_number: str,
    issue_date: date,
    due_date: date,
    competence_date: date | None,
    amount: Decimal,
    supplier_id: int | None,
    category_id: int | None,
    cost_center_id: int | None,
    payment_method_id: int | None,
    bank_account_id: int | None,
    assigned_user_id: int | None,
    notes: str,
    user_id: int | None,
) -> BPOFinancialPayable:
    payable = _load_payable_for_update(db, payable_id)
    if payable.status in {"pago", "cancelado"}:
        raise ValueError("Somente titulos abertos ou parciais podem ser editados.")

    normalized_amount = _money(amount)
    if normalized_amount <= Decimal("0.00"):
        raise ValueError("O valor do titulo precisa ser maior que zero.")
    if normalized_amount < _money(payable.paid_amount):
        raise ValueError("O valor do titulo nao pode ficar menor que o total ja pago.")

    _require_client_reference(db, BPOFinancialSupplier, item_id=supplier_id, client_id=payable.client_id, label="Fornecedor")
    _require_client_reference(db, BPOFinancialCategory, item_id=category_id, client_id=payable.client_id, label="Categoria")
    _require_client_reference(db, BPOFinancialCostCenter, item_id=cost_center_id, client_id=payable.client_id, label="Centro de custo")
    _require_client_reference(db, BPOFinancialPaymentMethod, item_id=payment_method_id, client_id=payable.client_id, label="Forma de pagamento")
    _require_client_reference(db, BPOFinancialBankAccount, item_id=bank_account_id, client_id=payable.client_id, label="Conta bancaria")
    _require_assigned_user(db, assigned_user_id)

    payable.title = title.strip()
    payable.description = description.strip()
    payable.document_number = document_number.strip()
    payable.issue_date = issue_date
    payable.due_date = due_date
    payable.competence_date = competence_date
    payable.amount = normalized_amount
    payable.supplier_id = supplier_id
    payable.category_id = category_id
    payable.cost_center_id = cost_center_id
    payable.payment_method_id = payment_method_id
    payable.bank_account_id = bank_account_id
    payable.assigned_user_id = assigned_user_id
    payable.notes = notes.strip()
    _recalculate_payable_status(db, payable)
    _register_event(
        db,
        payable_id=payable.id,
        user_id=user_id,
        event_type="atualizado",
        description="Dados do titulo atualizados.",
    )
    db.commit()
    return _load_payable_for_update(db, payable.id)


def register_payable_payment(
    db: Session,
    *,
    payable_id: int,
    payment_date: date,
    amount: Decimal,
    bank_account_id: int | None,
    reference: str,
    notes: str,
    created_by_user_id: int | None,
) -> BPOFinancialPayable:
    payable = _load_payable_for_update(db, payable_id)
    if payable.status == "cancelado":
        raise ValueError("Nao e possivel registrar baixa em titulo cancelado.")
    if payable.status == "pago":
        raise ValueError("O titulo ja esta totalmente pago.")

    normalized_amount = _money(amount)
    if normalized_amount <= Decimal("0.00"):
        raise ValueError("O valor da baixa precisa ser maior que zero.")
    remaining_amount = _money(payable.amount) - _money(payable.paid_amount)
    if normalized_amount > remaining_amount:
        raise ValueError("A baixa nao pode exceder o valor em aberto do titulo.")

    _require_client_reference(db, BPOFinancialBankAccount, item_id=bank_account_id, client_id=payable.client_id, label="Conta bancaria")

    payment = BPOFinancialPayablePayment(
        payable_id=payable.id,
        bank_account_id=bank_account_id,
        payment_date=payment_date,
        amount=normalized_amount,
        reference=reference.strip(),
        notes=notes.strip(),
        created_by_user_id=created_by_user_id,
    )
    db.add(payment)
    db.flush()

    if bank_account_id:
        payable.bank_account_id = bank_account_id
    _recalculate_payable_status(db, payable)
    _register_event(
        db,
        payable_id=payable.id,
        user_id=created_by_user_id,
        event_type="baixa",
        description=f"Baixa registrada no valor de {normalized_amount}.",
    )
    db.commit()
    return _load_payable_for_update(db, payable.id)


def cancel_payable(
    db: Session,
    *,
    payable_id: int,
    user_id: int | None,
    reason: str = "",
) -> BPOFinancialPayable:
    payable = _load_payable_for_update(db, payable_id)
    if payable.status == "cancelado":
        raise ValueError("O titulo ja esta cancelado.")
    if _money(payable.paid_amount) > Decimal("0.00"):
        raise ValueError("Nao e possivel cancelar um titulo que ja possui baixa registrada.")
    payable.status = "cancelado"
    payable.cancelled_at = datetime.utcnow()
    _register_event(
        db,
        payable_id=payable.id,
        user_id=user_id,
        event_type="cancelado",
        description=reason.strip() or "Titulo cancelado.",
    )
    db.commit()
    return _load_payable_for_update(db, payable.id)


def reactivate_payable(
    db: Session,
    *,
    payable_id: int,
    user_id: int | None,
    note: str = "",
) -> BPOFinancialPayable:
    payable = _load_payable_for_update(db, payable_id)
    if payable.status != "cancelado":
        raise ValueError("Somente titulos cancelados podem ser reativados.")
    payable.cancelled_at = None
    payable.status = "aberto"
    _recalculate_payable_status(db, payable)
    _register_event(
        db,
        payable_id=payable.id,
        user_id=user_id,
        event_type="reativado",
        description=note.strip() or "Titulo reativado.",
    )
    db.commit()
    return _load_payable_for_update(db, payable.id)
