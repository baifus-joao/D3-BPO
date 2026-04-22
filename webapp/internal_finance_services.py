from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal, ROUND_DOWN
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from conciliador.service import ConciliationUserError

from .erp import transaction_query
from .internal_finance_catalog import display_financial_category
from .models import FinancialCategory, FinancialTransaction


ENTRY_MODE_LABELS = {
    "avista": "A vista",
    "parcelado": "Parcelado",
    "projecao": "Projecao",
}

TRANSACTION_TYPE_LABELS = {
    "SAIDA": "Conta a pagar",
    "ENTRADA": "Conta a receber",
}


def normalize_entry_mode(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in ENTRY_MODE_LABELS else "avista"


def normalize_transaction_type(value: str | None) -> str:
    normalized = str(value or "").strip().upper()
    return normalized if normalized in {"ENTRADA", "SAIDA"} else "SAIDA"


def normalize_transaction_status(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in {"previsto", "realizado"} else "previsto"


def normalize_text(value: str | None) -> str:
    return str(value or "").strip()


def decimal_to_input(value: Decimal | int | float | str | None) -> str:
    return f"{Decimal(str(value or 0)).quantize(Decimal('0.01')):.2f}"


def parse_amount_input(value: str | Decimal | int | float | None) -> Decimal:
    text = str(value or "0").strip().replace("R$", "").replace(".", "").replace(",", ".")
    return Decimal(text or "0").copy_abs().quantize(Decimal("0.01"))


def _add_months(base_date: date, months: int) -> date:
    month_index = base_date.month - 1 + months
    year = base_date.year + (month_index // 12)
    month = (month_index % 12) + 1
    day = min(base_date.day, monthrange(year, month)[1])
    return date(year, month, day)


def _distribute_amount(total_amount: Decimal, count: int) -> list[Decimal]:
    normalized_total = Decimal(total_amount).quantize(Decimal("0.01"))
    base_value = (normalized_total / count).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    remainder = normalized_total - (base_value * count)
    values: list[Decimal] = []
    cent = Decimal("0.01")
    for _ in range(count):
        current = base_value
        if remainder > Decimal("0"):
            current += cent
            remainder -= cent
        values.append(current)
    return values


def build_installment_schedule(*, total_amount: Decimal, first_date: date, installment_count: int) -> list[dict[str, object]]:
    if installment_count < 2:
        raise ConciliationUserError("Informe pelo menos 2 parcelas para o lancamento parcelado.")
    values = _distribute_amount(total_amount, installment_count)
    rows = []
    for index, amount in enumerate(values, start=1):
        rows.append(
            {
                "label": f"Parcela {index}/{installment_count}",
                "date": _add_months(first_date, index - 1),
                "amount": amount,
            }
        )
    return rows


def build_projection_schedule(*, projected_amount: Decimal, period_start: date, period_end: date) -> list[dict[str, object]]:
    if period_end < period_start:
        raise ConciliationUserError("O periodo final da projecao nao pode ser anterior ao inicial.")

    rows: list[dict[str, object]] = []
    cursor = period_start
    position = 1
    while cursor <= period_end:
        rows.append(
            {
                "label": f"Projecao {position}",
                "period_label": cursor.strftime("%m/%Y"),
                "date": cursor,
                "amount": Decimal(projected_amount).quantize(Decimal("0.01")),
            }
        )
        cursor = _add_months(cursor, 1)
        position += 1
    return rows


def parse_schedule_rows(
    *,
    mode: str,
    transaction_date: date | None,
    amount: Decimal,
    installment_count: int,
    schedule_dates: list[str],
    schedule_amounts: list[str],
    schedule_labels: list[str],
    projection_start: date | None,
    projection_end: date | None,
) -> tuple[list[dict[str, object]], tuple[date, date] | None]:
    normalized_mode = normalize_entry_mode(mode)

    if normalized_mode == "avista":
        effective_date = transaction_date or date.today()
        return [
            {
                "label": "Lancamento unico",
                "date": effective_date,
                "amount": amount.quantize(Decimal("0.01")),
            }
        ], None

    if normalized_mode == "parcelado":
        if schedule_dates and schedule_amounts:
            rows: list[dict[str, object]] = []
            for index, row_date in enumerate(schedule_dates):
                parsed_date = date.fromisoformat(row_date)
                row_amount = parse_amount_input(schedule_amounts[index] if index < len(schedule_amounts) else "0")
                label = schedule_labels[index] if index < len(schedule_labels) and schedule_labels[index] else f"Parcela {index + 1}/{len(schedule_dates)}"
                rows.append({"label": label, "date": parsed_date, "amount": row_amount})
            if len(rows) < 2:
                raise ConciliationUserError("Informe ao menos 2 parcelas para salvar o lancamento parcelado.")
            return rows, None
        if not transaction_date:
            raise ConciliationUserError("Informe a data da primeira parcela.")
        return build_installment_schedule(
            total_amount=amount,
            first_date=transaction_date,
            installment_count=installment_count,
        ), None

    if not projection_start or not projection_end:
        raise ConciliationUserError("Informe o periodo completo da projecao.")

    if schedule_dates and schedule_amounts:
        rows = []
        for index, row_date in enumerate(schedule_dates):
            parsed_date = date.fromisoformat(row_date)
            row_amount = parse_amount_input(schedule_amounts[index] if index < len(schedule_amounts) else "0")
            label = schedule_labels[index] if index < len(schedule_labels) and schedule_labels[index] else parsed_date.strftime("%m/%Y")
            rows.append({"label": label, "date": parsed_date, "amount": row_amount})
        if not rows:
            raise ConciliationUserError("Nenhuma linha de projecao foi gerada.")
        return rows, (projection_start, projection_end)

    return build_projection_schedule(
        projected_amount=amount,
        period_start=projection_start,
        period_end=projection_end,
    ), (projection_start, projection_end)


def load_internal_finance_form_prefill(db: Session, duplicate_id: int | None) -> dict[str, object]:
    defaults = {
        "type": "SAIDA",
        "entry_mode": "avista",
        "transaction_date": date.today().isoformat(),
        "description": "",
        "interested_party": "",
        "category_id": "",
        "subcategory": "",
        "amount": "",
        "payment_method_id": "",
        "bank_account_id": "",
        "store_id": "",
        "status": "previsto",
        "installment_count": 2,
        "projection_start": "",
        "projection_end": "",
        "schedule_rows": [],
        "duplicate_source": None,
    }
    if not duplicate_id:
        return {"form_defaults": defaults}

    item = db.scalar(
        transaction_query(db).where(FinancialTransaction.id == duplicate_id)
    )
    if not item:
        return {"form_defaults": defaults}

    siblings = load_group_transactions(db, item)
    mode = normalize_entry_mode(item.entry_mode)

    if mode == "parcelado":
        defaults["amount"] = decimal_to_input(sum((Decimal(row.amount) for row in siblings), Decimal("0")))
        defaults["installment_count"] = len(siblings)
        defaults["schedule_rows"] = [
            {
                "label": f"Parcela {row.installment_number or index}/{row.installment_total or len(siblings)}",
                "date": row.transaction_date.isoformat(),
                "amount": decimal_to_input(row.amount),
            }
            for index, row in enumerate(siblings, start=1)
        ]
    elif mode == "projecao":
        defaults["amount"] = decimal_to_input(siblings[0].amount if siblings else item.amount)
        defaults["projection_start"] = (siblings[0].projection_start or siblings[0].transaction_date).isoformat()
        defaults["projection_end"] = (siblings[0].projection_end or siblings[-1].transaction_date).isoformat()
        defaults["schedule_rows"] = [
            {
                "label": row.projection_label or row.transaction_date.strftime("%m/%Y"),
                "date": row.transaction_date.isoformat(),
                "amount": decimal_to_input(row.amount),
            }
            for row in siblings
        ]
    else:
        defaults["amount"] = decimal_to_input(item.amount)

    defaults.update(
        {
            "type": item.type,
            "entry_mode": mode,
            "transaction_date": siblings[0].transaction_date.isoformat() if siblings else item.transaction_date.isoformat(),
            "description": item.description,
            "interested_party": item.interested_party or "",
            "category_id": str(item.category_id or ""),
            "subcategory": item.subcategory or "",
            "payment_method_id": str(item.payment_method_id or ""),
            "bank_account_id": str(item.bank_account_id or ""),
            "store_id": str(item.store_id or ""),
            "status": item.status,
            "duplicate_source": {
                "id": item.id,
                "description": item.description,
                "mode_label": ENTRY_MODE_LABELS.get(mode, "A vista"),
                "group_size": len(siblings),
            },
        }
    )
    return {"form_defaults": defaults}


def load_group_transactions(db: Session, item: FinancialTransaction) -> list[FinancialTransaction]:
    if item.group_key:
        rows = db.scalars(
            transaction_query(db)
            .where(FinancialTransaction.group_key == item.group_key)
            .order_by(FinancialTransaction.transaction_date.asc(), FinancialTransaction.id.asc())
        ).all()
        if rows:
            return rows
    return [item]


def build_interested_party_suggestions(db: Session) -> list[str]:
    rows = db.scalars(
        select(FinancialTransaction.interested_party)
        .where(FinancialTransaction.interested_party != "")
        .order_by(FinancialTransaction.interested_party.asc())
    ).all()
    suggestions: list[str] = []
    seen: set[str] = set()
    for item in rows:
        normalized = normalize_text(item).lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        suggestions.append(str(item))
        if len(suggestions) >= 30:
            break
    return suggestions


def load_internal_finance_detail(
    db: Session,
    *,
    transaction_id: int,
    format_currency,
    format_short_date,
) -> dict[str, object] | None:
    item = db.scalar(
        transaction_query(db).where(FinancialTransaction.id == transaction_id)
    )
    if not item:
        return None

    siblings = load_group_transactions(db, item)
    mode = normalize_entry_mode(item.entry_mode)
    total_amount = sum((Decimal(row.amount) for row in siblings), Decimal("0"))
    return {
        "transaction": {
            "id": item.id,
            "description": item.description,
            "type": item.type,
            "type_label": TRANSACTION_TYPE_LABELS.get(item.type, item.type),
            "entry_mode": mode,
            "entry_mode_label": ENTRY_MODE_LABELS.get(mode, "A vista"),
            "interested_party": item.interested_party or "-",
            "category": display_financial_category(item.category.name) if item.category else "-",
            "subcategory": item.subcategory or "-",
            "status": item.status,
            "status_class": "success" if item.status == "realizado" else "warning",
            "payment_method": item.payment_method.name if item.payment_method else "-",
            "bank_account": item.bank_account.name if item.bank_account else "-",
            "store": item.store.name if item.store else "-",
            "transaction_date": format_short_date(item.transaction_date),
            "planned_date": format_short_date(item.planned_date),
            "realized_date": format_short_date(item.realized_date),
            "projection_start": format_short_date(item.projection_start),
            "projection_end": format_short_date(item.projection_end),
            "group_size": len(siblings),
            "group_total": format_currency(total_amount),
            "editable": item.source != "conciliacao",
            "duplicate_url": f"/gestao/financeiro/novo?duplicate_id={item.id}",
        },
        "related_rows": [
            {
                "id": row.id,
                "label": row.projection_label or (f"Parcela {row.installment_number}/{row.installment_total}" if row.installment_total else "Lancamento"),
                "date": format_short_date(row.transaction_date),
                "amount": format_currency(row.amount),
                "status": row.status,
                "status_class": "success" if row.status == "realizado" else "warning",
            }
            for row in siblings
        ],
    }


def create_internal_finance_entries(
    db: Session,
    *,
    user_id: int,
    transaction_type: str,
    entry_mode: str,
    description: str,
    interested_party: str,
    category_id: int | None,
    subcategory: str,
    amount: Decimal,
    payment_method_id: int | None,
    bank_account_id: int | None,
    store_id: int | None,
    status: str,
    schedule_rows: list[dict[str, object]],
    projection_period: tuple[date, date] | None,
) -> list[FinancialTransaction]:
    normalized_type = normalize_transaction_type(transaction_type)
    normalized_mode = normalize_entry_mode(entry_mode)
    normalized_status = normalize_transaction_status(status)
    normalized_description = normalize_text(description)
    normalized_interested = normalize_text(interested_party)
    normalized_subcategory = normalize_text(subcategory)

    if not normalized_description:
        raise ConciliationUserError("Informe a descricao do lancamento.")
    if not normalized_interested:
        raise ConciliationUserError("Informe o interessado da conta.")
    if not category_id:
        raise ConciliationUserError("Selecione uma categoria.")
    if not normalized_subcategory:
        raise ConciliationUserError("Informe a subcategoria.")
    if amount <= Decimal("0"):
        raise ConciliationUserError("Informe um valor maior que zero.")

    category = db.get(FinancialCategory, category_id)
    if not category or not category.is_active:
        raise ConciliationUserError("Categoria financeira invalida.")
    if category.type != normalized_type:
        raise ConciliationUserError("A categoria escolhida nao corresponde ao tipo do lancamento.")

    if not schedule_rows:
        raise ConciliationUserError("Nenhuma linha financeira foi gerada para salvar.")

    group_key = uuid4().hex if normalized_mode != "avista" or len(schedule_rows) > 1 else ""
    rows: list[FinancialTransaction] = []
    for index, row in enumerate(schedule_rows, start=1):
        transaction_date = row["date"]
        row_amount = Decimal(str(row["amount"])).quantize(Decimal("0.01"))
        tx = FinancialTransaction(
            transaction_date=transaction_date,
            type=normalized_type,
            description=normalized_description,
            interested_party=normalized_interested,
            category_id=category_id,
            subcategory=normalized_subcategory,
            amount=row_amount,
            payment_method_id=payment_method_id,
            bank_account_id=bank_account_id,
            store_id=store_id,
            source="manual",
            source_reference=group_key or "",
            status=normalized_status,
            planned_date=transaction_date,
            realized_date=transaction_date if normalized_status == "realizado" else None,
            created_by_user_id=user_id,
            entry_mode=normalized_mode,
            group_key=group_key or None,
            installment_number=index if normalized_mode == "parcelado" else None,
            installment_total=len(schedule_rows) if normalized_mode == "parcelado" else None,
            projection_label=str(row.get("label", "")) if normalized_mode == "projecao" else "",
            projection_start=projection_period[0] if projection_period else None,
            projection_end=projection_period[1] if projection_period else None,
        )
        db.add(tx)
        rows.append(tx)

    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


def build_schedule_preview_payload(rows: list[dict[str, object]]) -> list[dict[str, str]]:
    return [
        {
            "label": str(row["label"]),
            "date": row["date"].isoformat(),
            "amount": decimal_to_input(row["amount"]),
        }
        for row in rows
    ]
