from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from conciliador.core.aggregations import paid_sales_missing_receipt
from conciliador.core.parsers import load_recebimentos, load_vendas
from conciliador.service import ConciliationResult

from .bpo_models import (
    BPOClient,
    BPOClientContact,
    BPOConciliationItem,
    BPOConciliationRun,
    BPOTask,
    BPOTaskEvent,
    BPOTaskTemplate,
)
from .models import User


TASK_STATUS_LABELS = {
    "pendente": "Pendente",
    "em_execucao": "Em execucao",
    "aguardando_cliente": "Aguardando cliente",
    "concluida": "Concluida",
    "atrasada": "Atrasada",
}

TASK_STATUS_CLASS = {
    "pendente": "neutral",
    "em_execucao": "warning",
    "aguardando_cliente": "warning",
    "concluida": "success",
    "atrasada": "error",
}

CLIENT_STATUS_LABELS = {
    "ativo": "Ativo",
    "implantacao": "Implantacao",
    "pausado": "Pausado",
    "inativo": "Inativo",
}

PRIORITY_LABELS = {
    "baixa": "Baixa",
    "normal": "Normal",
    "alta": "Alta",
}

PENDING_ITEM_STATUS_LABELS = {
    "aberto": "Aberto",
    "em_analise": "Em analise",
    "aguardando_cliente": "Aguardando cliente",
    "resolvido": "Resolvido",
    "descartado": "Descartado",
}

PENDING_ITEM_STATUS_CLASS = {
    "aberto": "error",
    "em_analise": "warning",
    "aguardando_cliente": "warning",
    "resolvido": "success",
    "descartado": "neutral",
}


def _optional_decimal(value) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return Decimal(text)


def seed_bpo_data(db: Session) -> None:
    defaults = [
        ("Conciliacao mensal", "conciliacao", 2, True),
        ("Fechamento financeiro", "fechamento", 3, True),
        ("Contas a pagar", "pagamentos", 1, True),
    ]
    for name, service_type, sla_days, requires_competence in defaults:
        exists = db.scalar(select(BPOTaskTemplate).where(BPOTaskTemplate.name == name))
        if exists:
            continue
        db.add(
            BPOTaskTemplate(
                name=name,
                service_type=service_type,
                default_sla_days=sla_days,
                requires_competence=requires_competence,
                is_active=True,
            )
        )
    db.commit()


def _task_status(task: BPOTask) -> str:
    if task.status == "concluida":
        return "concluida"
    if task.due_date and task.due_date < date.today():
        return "atrasada"
    return task.status


def _serialize_task(task: BPOTask) -> dict[str, object]:
    effective_status = _task_status(task)
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "title_raw": task.title,
        "description_raw": task.description,
        "status": effective_status,
        "status_label": TASK_STATUS_LABELS.get(effective_status, effective_status.replace("_", " ").title()),
        "status_class": TASK_STATUS_CLASS.get(effective_status, "neutral"),
        "priority": task.priority,
        "priority_label": PRIORITY_LABELS.get(task.priority, task.priority.title()),
        "assigned_user_id": task.assigned_user_id,
        "client_name": task.client.trade_name or task.client.legal_name,
        "client_id": task.client_id,
        "assignee_name": task.assigned_user.name if task.assigned_user else "Sem responsavel",
        "due_date": task.due_date.strftime("%d/%m/%Y") if task.due_date else "-",
        "due_date_iso": task.due_date.isoformat() if task.due_date else "",
        "competence_date": task.competence_date.strftime("%m/%Y") if task.competence_date else "-",
        "competence_date_iso": task.competence_date.isoformat() if task.competence_date else "",
        "can_start": effective_status in {"pendente", "atrasada"},
        "can_wait": effective_status in {"pendente", "em_execucao", "atrasada"},
        "can_complete": effective_status in {"em_execucao", "aguardando_cliente", "atrasada"},
    }


def _serialize_client(client: BPOClient, *, task_count: int = 0, overdue_count: int = 0, last_run_at: datetime | None = None) -> dict[str, object]:
    primary_contact = next((item for item in client.contacts if item.is_primary), client.contacts[0] if client.contacts else None)
    return {
        "id": client.id,
        "legal_name": client.legal_name,
        "trade_name": client.trade_name or client.legal_name,
        "notes": client.notes,
        "document": client.document or "-",
        "segment": client.segment or "-",
        "status": client.status,
        "status_label": CLIENT_STATUS_LABELS.get(client.status, client.status.title()),
        "responsible_user_id": client.responsible_user_id,
        "responsible_name": client.responsible_user.name if client.responsible_user else "Sem responsavel",
        "task_count": task_count,
        "overdue_count": overdue_count,
        "last_run_at": last_run_at.strftime("%d/%m/%Y %H:%M") if last_run_at else "Sem conciliacao",
        "primary_contact": primary_contact,
    }


def _serialize_pending_item(item: BPOConciliationItem) -> dict[str, object]:
    run = item.conciliation_run
    client = run.client if run else None
    normalized_status = item.status if item.status in PENDING_ITEM_STATUS_LABELS else "aberto"
    return {
        "id": item.id,
        "item_type": item.item_type,
        "reference_key": item.reference_key or "-",
        "status": normalized_status,
        "status_label": PENDING_ITEM_STATUS_LABELS[normalized_status],
        "status_class": PENDING_ITEM_STATUS_CLASS[normalized_status],
        "detail": item.detail or "",
        "client_id": client.id if client else None,
        "client_name": (client.trade_name or client.legal_name) if client else "Cliente removido",
        "period": f"{run.period_start.strftime('%d/%m/%Y')} ate {run.period_end.strftime('%d/%m/%Y')}" if run else "-",
        "sale_date": item.sale_date.strftime("%d/%m/%Y") if item.sale_date else "-",
        "expected_payment_date": item.expected_payment_date.strftime("%d/%m/%Y") if item.expected_payment_date else "-",
        "gross_amount": item.gross_amount,
        "net_amount": item.net_amount,
        "created_at": item.created_at.strftime("%d/%m/%Y %H:%M"),
        "conciliation_run_id": run.id if run else None,
    }


def load_client_reference_lists(db: Session) -> dict[str, object]:
    clients = db.scalars(
        select(BPOClient)
        .options(selectinload(BPOClient.contacts), selectinload(BPOClient.responsible_user))
        .order_by(BPOClient.trade_name.asc(), BPOClient.legal_name.asc())
    ).all()
    users = db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.name.asc())).all()
    templates = db.scalars(
        select(BPOTaskTemplate).where(BPOTaskTemplate.is_active.is_(True)).order_by(BPOTaskTemplate.name.asc())
    ).all()
    return {"clients": clients, "users": users, "task_templates": templates}


def load_operations_queue(db: Session, *, filters: dict[str, object] | None = None) -> dict[str, object]:
    filters = filters or {}
    client_id = filters.get("client_id")
    status = filters.get("status")
    assigned_user_id = filters.get("assigned_user_id")

    task_query = (
        select(BPOTask)
        .options(selectinload(BPOTask.client), selectinload(BPOTask.assigned_user))
        .where(BPOTask.status != "concluida")
    )
    if client_id:
        task_query = task_query.where(BPOTask.client_id == client_id)
    if status:
        if status == "atrasada":
            task_query = task_query.where(BPOTask.due_date < date.today())
        else:
            task_query = task_query.where(BPOTask.status == status)
    if assigned_user_id:
        task_query = task_query.where(BPOTask.assigned_user_id == assigned_user_id)

    tasks = db.scalars(
        task_query.order_by(BPOTask.due_date.asc().nulls_last(), BPOTask.created_at.asc()).limit(12)
    ).all()
    clients = db.scalars(
        select(BPOClient)
        .options(
            selectinload(BPOClient.contacts),
            selectinload(BPOClient.responsible_user),
            selectinload(BPOClient.tasks),
            selectinload(BPOClient.conciliation_runs),
        )
        .order_by(BPOClient.trade_name.asc(), BPOClient.legal_name.asc())
        .limit(6)
    ).all()
    recent_runs = db.scalars(
        select(BPOConciliationRun)
        .options(selectinload(BPOConciliationRun.client), selectinload(BPOConciliationRun.uploaded_by))
        .order_by(desc(BPOConciliationRun.created_at))
        .limit(6)
    ).all()

    total_clients = int(db.scalar(select(func.count()).select_from(BPOClient).where(BPOClient.status != "inativo")) or 0)
    total_pending = int(db.scalar(select(func.count()).select_from(BPOTask).where(BPOTask.status != "concluida")) or 0)
    waiting_client = int(db.scalar(select(func.count()).select_from(BPOTask).where(BPOTask.status == "aguardando_cliente")) or 0)
    open_pending_items = int(
        db.scalar(
            select(func.count()).select_from(BPOConciliationItem).where(
                BPOConciliationItem.status.in_(["aberto", "em_analise", "aguardando_cliente"])
            )
        )
        or 0
    )
    overdue = int(
        db.scalar(
            select(func.count()).select_from(BPOTask).where(BPOTask.status != "concluida", BPOTask.due_date < date.today())
        )
        or 0
    )

    serialized_tasks = []
    for task in tasks:
        data = _serialize_task(task)
        serialized_tasks.append(data)

    client_cards = []
    for client in clients:
        open_tasks = [task for task in client.tasks if task.status != "concluida"]
        overdue_count = sum(1 for task in open_tasks if task.due_date and task.due_date < date.today())
        latest_run = max((run.created_at for run in client.conciliation_runs), default=None)
        client_cards.append(_serialize_client(client, task_count=len(open_tasks), overdue_count=overdue_count, last_run_at=latest_run))

    runs = [
        {
            "id": run.id,
            "client_name": run.client.trade_name or run.client.legal_name,
            "period": f"{run.period_start.strftime('%d/%m/%Y')} ate {run.period_end.strftime('%d/%m/%Y')}",
            "status": run.status,
            "status_class": "success" if run.status == "concluida" else "warning",
            "divergences": run.total_divergencias,
            "executed_at": run.created_at.strftime("%d/%m/%Y %H:%M"),
            "user_name": run.uploaded_by.name if run.uploaded_by else "Sistema",
        }
        for run in recent_runs
    ]

    return {
        "queue_metrics": [
            {"label": "Clientes ativos", "value": total_clients},
            {"label": "Tarefas abertas", "value": total_pending},
            {"label": "Aguardando cliente", "value": waiting_client},
            {"label": "Pendencias abertas", "value": open_pending_items},
            {"label": "Atrasadas", "value": overdue},
        ],
        "queue_tasks": serialized_tasks,
        "client_cards": client_cards,
        "recent_runs": runs,
        "queue_filters": {
            "client_id": client_id,
            "status": status or "",
            "assigned_user_id": assigned_user_id,
        },
    }


def load_clients_overview(db: Session, *, filters: dict[str, object] | None = None) -> dict[str, object]:
    filters = filters or {}
    status = filters.get("status")
    responsible_user_id = filters.get("responsible_user_id")
    search = str(filters.get("search") or "").strip()
    normalized_search = search.lower()

    client_query = (
        select(BPOClient)
        .options(
            selectinload(BPOClient.contacts),
            selectinload(BPOClient.tasks),
            selectinload(BPOClient.conciliation_runs),
            selectinload(BPOClient.responsible_user),
        )
    )
    if status:
        client_query = client_query.where(BPOClient.status == status)
    if responsible_user_id:
        client_query = client_query.where(BPOClient.responsible_user_id == responsible_user_id)
    clients = db.scalars(client_query.order_by(BPOClient.trade_name.asc(), BPOClient.legal_name.asc())).all()
    rows = []
    for client in clients:
        open_tasks = [task for task in client.tasks if task.status != "concluida"]
        overdue_count = sum(1 for task in open_tasks if task.due_date and task.due_date < date.today())
        latest_run = max((run.created_at for run in client.conciliation_runs), default=None)
        row = _serialize_client(client, task_count=len(open_tasks), overdue_count=overdue_count, last_run_at=latest_run)
        haystack = " ".join([row["trade_name"], row["legal_name"], row["document"], row["segment"], row["responsible_name"]]).lower()
        if normalized_search and normalized_search not in haystack:
            continue
        rows.append(row)
    return {
        "client_metrics": [
            {"label": "Carteira", "value": len(rows)},
            {"label": "Com atraso", "value": sum(1 for row in rows if row["overdue_count"])},
            {"label": "Sem responsavel", "value": sum(1 for row in rows if row["responsible_name"] == "Sem responsavel")},
            {"label": "Sem contato", "value": sum(1 for row in rows if not row["primary_contact"])},
        ],
        "client_rows": rows,
        "client_filters": {
            "status": status or "",
            "responsible_user_id": responsible_user_id,
            "search": search,
        },
    }


def load_client_detail(db: Session, client_id: int) -> dict[str, object] | None:
    client = db.scalar(
        select(BPOClient)
        .where(BPOClient.id == client_id)
        .options(
            selectinload(BPOClient.contacts),
            selectinload(BPOClient.responsible_user),
            selectinload(BPOClient.tasks).selectinload(BPOTask.assigned_user),
            selectinload(BPOClient.tasks).selectinload(BPOTask.events).selectinload(BPOTaskEvent.user),
            selectinload(BPOClient.conciliation_runs).selectinload(BPOConciliationRun.items),
        )
    )
    if not client:
        return None

    tasks = sorted(client.tasks, key=lambda item: (item.completed_at is not None, item.due_date or date.max, item.created_at))
    runs = sorted(client.conciliation_runs, key=lambda item: item.created_at, reverse=True)

    return {
        "client": _serialize_client(
            client,
            task_count=sum(1 for task in tasks if task.status != "concluida"),
            overdue_count=sum(1 for task in tasks if task.due_date and task.due_date < date.today() and task.status != "concluida"),
            last_run_at=runs[0].created_at if runs else None,
        ),
        "contacts": client.contacts,
        "tasks": [_serialize_task(task) for task in tasks[:20]],
        "task_events": [
            {
                "task_id": event.task_id,
                "event_type": event.event_type,
                "note": event.note,
                "user_name": event.user.name if event.user else "Sistema",
                "created_at": event.created_at.strftime("%d/%m/%Y %H:%M"),
            }
            for task in tasks[:10]
            for event in sorted(task.events, key=lambda item: item.created_at, reverse=True)[:3]
        ],
        "conciliation_runs": [
            {
                "id": run.id,
                "period": f"{run.period_start.strftime('%d/%m/%Y')} ate {run.period_end.strftime('%d/%m/%Y')}",
                "status": run.status,
                "status_class": "success" if run.status == "concluida" else "warning",
                "divergences": run.total_divergencias,
                "arquivo_saida": run.arquivo_saida,
                "executed_at": run.created_at.strftime("%d/%m/%Y %H:%M"),
            }
            for run in runs[:12]
        ],
        "pending_items": [
            _serialize_pending_item(item)
            for run in runs[:8]
            for item in run.items
            if item.status in {"aberto", "em_analise", "aguardando_cliente"}
        ][:12],
    }


def load_pending_items(db: Session, *, filters: dict[str, object] | None = None) -> dict[str, object]:
    filters = filters or {}
    client_id = filters.get("client_id")
    status = filters.get("status")
    item_type = str(filters.get("item_type") or "").strip()

    query = (
        select(BPOConciliationItem)
        .options(selectinload(BPOConciliationItem.conciliation_run).selectinload(BPOConciliationRun.client))
        .join(BPOConciliationRun, BPOConciliationRun.id == BPOConciliationItem.conciliation_run_id)
        .order_by(BPOConciliationItem.created_at.desc())
    )
    if client_id:
        query = query.where(BPOConciliationRun.client_id == client_id)
    if status:
        query = query.where(BPOConciliationItem.status == status)
    if item_type:
        query = query.where(BPOConciliationItem.item_type == item_type)

    items = db.scalars(query.limit(100)).all()
    open_count = int(
        db.scalar(
            select(func.count()).select_from(BPOConciliationItem).where(
                BPOConciliationItem.status.in_(["aberto", "em_analise", "aguardando_cliente"])
            )
        )
        or 0
    )
    resolved_count = int(
        db.scalar(select(func.count()).select_from(BPOConciliationItem).where(BPOConciliationItem.status == "resolvido")) or 0
    )
    waiting_client_count = int(
        db.scalar(select(func.count()).select_from(BPOConciliationItem).where(BPOConciliationItem.status == "aguardando_cliente")) or 0
    )

    item_types = sorted({item.item_type for item in items if item.item_type})

    return {
        "pending_metrics": [
            {"label": "Pendencias abertas", "value": open_count},
            {"label": "Aguardando cliente", "value": waiting_client_count},
            {"label": "Resolvidas", "value": resolved_count},
            {"label": "Itens filtrados", "value": len(items)},
        ],
        "pending_items": [_serialize_pending_item(item) for item in items],
        "pending_filters": {
            "client_id": client_id,
            "status": status or "",
            "item_type": item_type,
        },
        "pending_item_types": item_types,
    }


def create_task(
    db: Session,
    *,
    client_id: int,
    title: str,
    description: str,
    created_by_user_id: int | None,
    assigned_user_id: int | None,
    task_template_id: int | None = None,
    competence_date: date | None = None,
    due_date: date | None = None,
    priority: str = "normal",
) -> BPOTask:
    task = BPOTask(
        client_id=client_id,
        task_template_id=task_template_id,
        title=title.strip(),
        description=description.strip(),
        created_by_user_id=created_by_user_id,
        assigned_user_id=assigned_user_id,
        competence_date=competence_date,
        due_date=due_date,
        priority=priority if priority in PRIORITY_LABELS else "normal",
        status="pendente",
    )
    db.add(task)
    db.flush()
    db.add(
        BPOTaskEvent(
            task_id=task.id,
            user_id=created_by_user_id,
            event_type="criada",
            note="Tarefa criada no painel operacional.",
        )
    )
    db.commit()
    return task


def update_task_status(
    db: Session,
    *,
    task_id: int,
    status_value: str,
    user_id: int | None,
    note: str = "",
) -> BPOTask | None:
    task = db.get(BPOTask, task_id)
    if not task:
        return None
    normalized = status_value if status_value in TASK_STATUS_LABELS else "pendente"
    task.status = normalized
    if normalized == "em_execucao" and task.started_at is None:
        task.started_at = datetime.utcnow()
    if normalized == "concluida":
        task.completed_at = datetime.utcnow()
    elif normalized != "concluida":
        task.completed_at = None
    db.add(
        BPOTaskEvent(
            task_id=task.id,
            user_id=user_id,
            event_type="status",
            note=note.strip() or f"Status alterado para {TASK_STATUS_LABELS[normalized].lower()}.",
        )
    )
    db.commit()
    return task


def create_client_contact(
    db: Session,
    *,
    client_id: int,
    name: str,
    email: str,
    phone: str,
    role: str,
    is_primary: bool,
) -> BPOClientContact:
    if is_primary:
        for item in db.scalars(select(BPOClientContact).where(BPOClientContact.client_id == client_id)).all():
            item.is_primary = False
    contact = BPOClientContact(
        client_id=client_id,
        name=name.strip(),
        email=email.strip(),
        phone=phone.strip(),
        role=role.strip(),
        is_primary=is_primary,
    )
    db.add(contact)
    db.commit()
    return contact


def create_client(
    db: Session,
    *,
    legal_name: str,
    trade_name: str,
    document: str,
    segment: str,
    responsible_user_id: int | None,
    notes: str,
) -> BPOClient:
    client = BPOClient(
        legal_name=legal_name.strip(),
        trade_name=trade_name.strip(),
        document=document.strip(),
        segment=segment.strip(),
        responsible_user_id=responsible_user_id,
        notes=notes.strip(),
        status="ativo",
    )
    db.add(client)
    db.commit()
    return client


def update_client(
    db: Session,
    *,
    client_id: int,
    legal_name: str,
    trade_name: str,
    document: str,
    segment: str,
    responsible_user_id: int | None,
    notes: str,
    status: str,
) -> BPOClient | None:
    client = db.get(BPOClient, client_id)
    if not client:
        return None
    client.legal_name = legal_name.strip()
    client.trade_name = (trade_name or legal_name).strip()
    client.document = document.strip()
    client.segment = segment.strip()
    client.responsible_user_id = responsible_user_id
    client.notes = notes.strip()
    client.status = status if status in CLIENT_STATUS_LABELS else "ativo"
    db.commit()
    return client


def archive_client(db: Session, *, client_id: int) -> BPOClient | None:
    client = db.get(BPOClient, client_id)
    if not client:
        return None
    client.status = "inativo"
    db.commit()
    return client


def create_default_task_for_conciliation(
    db: Session,
    *,
    client_id: int,
    created_by_user_id: int | None,
    assigned_user_id: int | None,
    competence_date: date,
    due_date: date | None = None,
) -> BPOTask:
    template = db.scalar(select(BPOTaskTemplate).where(BPOTaskTemplate.service_type == "conciliacao"))
    due_date = due_date or (competence_date + timedelta(days=2))
    title = f"Conciliacao {competence_date.strftime('%m/%Y')}"
    return create_task(
        db,
        client_id=client_id,
        title=title,
        description="Tarefa gerada automaticamente a partir de uma conciliacao sem tarefa previa.",
        created_by_user_id=created_by_user_id,
        assigned_user_id=assigned_user_id,
        task_template_id=template.id if template else None,
        competence_date=competence_date,
        due_date=due_date,
        priority="normal",
    )


def load_client_open_tasks_for_conciliation(db: Session, client_id: int | None) -> list[BPOTask]:
    if not client_id:
        return []
    return db.scalars(
        select(BPOTask)
        .where(BPOTask.client_id == client_id, BPOTask.status != "concluida")
        .order_by(BPOTask.due_date.asc().nulls_last(), BPOTask.created_at.desc())
    ).all()


def update_task(
    db: Session,
    *,
    task_id: int,
    title: str,
    description: str,
    assigned_user_id: int | None,
    competence_date: date | None,
    due_date: date | None,
    priority: str,
) -> BPOTask | None:
    task = db.get(BPOTask, task_id)
    if not task:
        return None
    task.title = title.strip()
    task.description = description.strip()
    task.assigned_user_id = assigned_user_id
    task.competence_date = competence_date
    task.due_date = due_date
    task.priority = priority if priority in PRIORITY_LABELS else "normal"
    db.commit()
    return task


def delete_task(db: Session, *, task_id: int) -> tuple[bool, str]:
    task = db.scalar(
        select(BPOTask)
        .where(BPOTask.id == task_id)
        .options(selectinload(BPOTask.conciliation_runs), selectinload(BPOTask.events))
    )
    if not task:
        return False, "Tarefa não encontrada."
    if task.conciliation_runs:
        return False, "Não é possível excluir uma tarefa que já possui conciliações vinculadas."
    db.delete(task)
    db.commit()
    return True, "Tarefa removida."


def update_pending_item_status(
    db: Session,
    *,
    item_id: int,
    status_value: str,
    user_id: int | None,
    note: str = "",
) -> BPOConciliationItem | None:
    item = db.scalar(
        select(BPOConciliationItem)
        .where(BPOConciliationItem.id == item_id)
        .options(selectinload(BPOConciliationItem.conciliation_run))
    )
    if not item:
        return None
    normalized = status_value if status_value in PENDING_ITEM_STATUS_LABELS else "aberto"
    item.status = normalized
    if note.strip():
        preserved = item.detail.strip()
        item.detail = f"{preserved}\n\n[{datetime.utcnow().strftime('%d/%m/%Y %H:%M UTC')}] {note.strip()}".strip()

    run = item.conciliation_run
    if run and run.task_id:
        db.add(
            BPOTaskEvent(
                task_id=run.task_id,
                user_id=user_id,
                event_type="pendencia",
                note=f"Pendência {item.reference_key or item.id} atualizada para {PENDING_ITEM_STATUS_LABELS[normalized].lower()}.",
            )
        )
    db.commit()
    return item


def persist_conciliation_run(
    db: Session,
    *,
    client_id: int,
    task_id: int | None,
    user_id: int | None,
    period_start: date,
    period_end: date,
    filenames: dict[str, str],
    download_name: str,
    result: ConciliationResult,
    duration_ms: int,
) -> BPOConciliationRun:
    vendas, _ = load_vendas(result.arquivo_vendas)
    recebimentos, _ = load_recebimentos(result.arquivo_recebimentos)
    missing_receipts = paid_sales_missing_receipt(vendas, recebimentos)

    run = BPOConciliationRun(
        client_id=client_id,
        task_id=task_id,
        period_start=period_start,
        period_end=period_end,
        status="concluida",
        uploaded_by_user_id=user_id,
        arquivo_vendas=filenames["vendas"],
        arquivo_recebimentos=filenames["recebimentos"],
        arquivo_saida=download_name,
        total_vendas=result.qtde_linhas_vendas,
        total_recebimentos=result.qtde_linhas_recebimentos,
        total_divergencias=int(len(missing_receipts.index)),
        duracao_ms=duration_ms,
    )
    db.add(run)
    db.flush()

    for row in missing_receipts.to_dict(orient="records"):
        raw_sale_date = row.get("Data Venda")
        raw_expected_payment = row.get("Data Prevista")
        gross_amount = row.get("Valor Parcela Venda")
        net_amount = row.get("Valor Liquido Venda")
        db.add(
            BPOConciliationItem(
                conciliation_run_id=run.id,
                item_type="venda_paga_sem_recebimento",
                reference_key=str(row.get("Chave Parcela") or ""),
                sale_date=raw_sale_date.date() if hasattr(raw_sale_date, "date") else raw_sale_date,
                expected_payment_date=raw_expected_payment.date() if hasattr(raw_expected_payment, "date") else raw_expected_payment,
                gross_amount=_optional_decimal(gross_amount),
                net_amount=_optional_decimal(net_amount),
                status="aberto",
                detail=str(row.get("Motivo") or "Divergencia registrada na conciliacao."),
            )
        )

    if task_id:
        update_task_status(
            db,
            task_id=task_id,
            status_value="concluida",
            user_id=user_id,
            note=f"Conciliacao concluida para o periodo {period_start.strftime('%m/%Y')}.",
        )
        run = db.get(BPOConciliationRun, run.id)

    db.commit()
    return run
