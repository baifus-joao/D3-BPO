from __future__ import annotations

from collections import defaultdict
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
    BPODemand,
    BPOProject,
    BPOTask,
    BPOTaskEvent,
    BPOTaskTimeEntry,
    BPOTaskTemplate,
    BPORecurringRoutine,
)
from .models import User
from .time_utils import utcnow


TASK_STATUS_LABELS = {
    "pendente": "Pendente",
    "em_execucao": "Em execução",
    "aguardando_cliente": "Em revisão",
    "concluida": "Concluída",
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
    "implantacao": "Implantação",
    "pausado": "Pausado",
    "inativo": "Inativo",
}

PRIORITY_LABELS = {
    "baixa": "Baixa",
    "normal": "Normal",
    "alta": "Alta",
}

PROJECT_TYPE_LABELS = {
    "implantacao": "Implantação",
    "rotina_mensal": "Rotina mensal",
    "organizacao_financeira": "Organização financeira",
    "conciliacao": "Conciliação",
    "fiscal": "Fiscal",
    "operacional": "Operacional",
}

PROJECT_STATUS_LABELS = {
    "ativo": "Ativo",
    "pausado": "Pausado",
    "concluido": "Concluído",
}

DEMAND_TYPE_LABELS = {
    "financeiro": "Financeiro",
    "fiscal": "Fiscal",
    "operacional": "Operacional",
}

DEMAND_STATUS_LABELS = {
    "aberta": "Aberta",
    "triagem": "Triagem",
    "convertida": "Convertida",
    "concluida": "Concluída",
}

DEMAND_SOURCE_LABELS = {
    "manual": "Manual",
    "whatsapp": "WhatsApp",
    "email": "E-mail",
}

PENDING_ITEM_STATUS_LABELS = {
    "aberto": "Aberto",
    "em_analise": "Em análise",
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
        ("Conciliação mensal", "conciliacao", 2, True),
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


def _task_board_column(status: str) -> str:
    if status in {"pendente", "atrasada"}:
        return "a_fazer"
    if status == "em_execucao":
        return "em_andamento"
    if status == "aguardando_cliente":
        return "em_revisao"
    return "concluidas"


def _priority_tone(priority: str) -> str:
    return {
        "alta": "error",
        "normal": "warning",
        "baixa": "success",
    }.get(priority, "neutral")


def _serialize_task(task: BPOTask) -> dict[str, object]:
    effective_status = _task_status(task)
    total_seconds = sum(entry.duration_seconds for entry in task.time_entries if entry.ended_at)
    active_entry_id = next((entry.id for entry in task.time_entries if entry.ended_at is None), None)
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
        "priority_tone": _priority_tone(task.priority),
        "assigned_user_id": task.assigned_user_id,
        "client_name": task.client.trade_name or task.client.legal_name,
        "client_id": task.client_id,
        "project_id": task.project_id,
        "project_name": task.project.name if task.project else "Sem projeto",
        "assignee_name": task.assigned_user.name if task.assigned_user else "Sem responsável",
        "due_date": task.due_date.strftime("%d/%m/%Y") if task.due_date else "-",
        "due_date_iso": task.due_date.isoformat() if task.due_date else "",
        "competence_date": task.competence_date.strftime("%m/%Y") if task.competence_date else "-",
        "competence_date_iso": task.competence_date.isoformat() if task.competence_date else "",
        "logged_time_seconds": total_seconds,
        "logged_time_label": _duration_label(total_seconds),
        "active_time_entry_id": active_entry_id,
        "board_column": _task_board_column(effective_status),
        "edit_href": f"/operacoes/gestor-tarefas/clientes/{task.client_id}",
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
        "contracted_plan": client.contracted_plan or "-",
        "sla_deadline_day": client.sla_deadline_day,
        "sla_label": f"Fechamento até dia {client.sla_deadline_day}" if client.sla_deadline_day else "Não definido",
        "team_label": client.team_label or "-",
        "status": client.status,
        "status_label": CLIENT_STATUS_LABELS.get(client.status, client.status.title()),
        "responsible_user_id": client.responsible_user_id,
        "responsible_name": client.responsible_user.name if client.responsible_user else "Sem responsável",
        "task_count": task_count,
        "overdue_count": overdue_count,
        "last_run_at": last_run_at.strftime("%d/%m/%Y %H:%M") if last_run_at else "Sem conciliação",
        "primary_contact": primary_contact,
    }


def _serialize_project(project: BPOProject) -> dict[str, object]:
    open_tasks = [task for task in project.tasks if _task_status(task) != "concluida"]
    open_demands = [demand for demand in project.demands if demand.status not in {"concluida", "convertida"}]
    done_tasks = [task for task in project.tasks if _task_status(task) == "concluida"]
    overdue_count = sum(1 for task in open_tasks if _task_status(task) == "atrasada")
    total_tasks = len(project.tasks)
    progress_percent = int(round((len(done_tasks) / total_tasks) * 100)) if total_tasks else 0
    return {
        "id": project.id,
        "name": project.name,
        "client_id": project.client_id,
        "client_name": project.client.trade_name or project.client.legal_name,
        "project_type": project.project_type,
        "project_type_label": PROJECT_TYPE_LABELS.get(project.project_type, project.project_type.replace("_", " ").title()),
        "status": project.status,
        "status_label": PROJECT_STATUS_LABELS.get(project.status, project.status.title()),
        "description": project.description,
        "responsible_user_id": project.responsible_user_id,
        "responsible_name": project.responsible_user.name if project.responsible_user else "Sem responsável",
        "start_date": project.start_date.strftime("%d/%m/%Y") if project.start_date else "-",
        "end_date": project.end_date.strftime("%d/%m/%Y") if project.end_date else "-",
        "start_date_iso": project.start_date.isoformat() if project.start_date else "",
        "end_date_iso": project.end_date.isoformat() if project.end_date else "",
        "task_count": len(open_tasks),
        "demand_count": len(open_demands),
        "done_task_count": len(done_tasks),
        "overdue_count": overdue_count,
        "progress_percent": progress_percent,
        "tasks_href": f"/operacoes/gestor-tarefas/tarefasproject_id={project.id}",
    }


def _duration_label(total_seconds: int) -> str:
    minutes = int(total_seconds // 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def _serialize_time_entry(entry: BPOTaskTimeEntry) -> dict[str, object]:
    active = entry.ended_at is None
    duration = entry.duration_seconds
    if active:
        now = utcnow()
        if entry.started_at.tzinfo is None and now.tzinfo is not None:
            now = now.replace(tzinfo=None)
        elif entry.started_at.tzinfo is not None and now.tzinfo is None:
            now = now.replace(tzinfo=entry.started_at.tzinfo)
        duration = max(int((now - entry.started_at).total_seconds()), duration)
    return {
        "id": entry.id,
        "task_id": entry.task_id,
        "task_title": entry.task.title,
        "client_name": entry.task.client.trade_name or entry.task.client.legal_name,
        "user_name": entry.user.name if entry.user else "Sem responsável",
        "started_at": entry.started_at.strftime("%d/%m/%Y %H:%M"),
        "ended_at": entry.ended_at.strftime("%d/%m/%Y %H:%M") if entry.ended_at else "Em andamento",
        "duration_seconds": duration,
        "duration_label": _duration_label(duration),
        "note": entry.note,
        "is_active": active,
    }


def _serialize_demand(demand: BPODemand) -> dict[str, object]:
    return {
        "id": demand.id,
        "title": demand.title,
        "description": demand.description,
        "client_id": demand.client_id,
        "client_name": demand.client.trade_name or demand.client.legal_name,
        "project_id": demand.project_id,
        "project_name": demand.project.name if demand.project else "Sem projeto",
        "source": demand.source,
        "source_label": DEMAND_SOURCE_LABELS.get(demand.source, demand.source.title()),
        "demand_type": demand.demand_type,
        "demand_type_label": DEMAND_TYPE_LABELS.get(demand.demand_type, demand.demand_type.title()),
        "priority": demand.priority,
        "priority_label": PRIORITY_LABELS.get(demand.priority, demand.priority.title()),
        "priority_tone": _priority_tone(demand.priority),
        "status": demand.status,
        "status_label": DEMAND_STATUS_LABELS.get(demand.status, demand.status.title()),
        "responsible_name": demand.responsible_user.name if demand.responsible_user else "Sem responsável",
        "responsible_user_id": demand.responsible_user_id,
        "due_date": demand.due_date.strftime("%d/%m/%Y") if demand.due_date else "-",
        "due_date_iso": demand.due_date.isoformat() if demand.due_date else "",
        "converted_task_id": demand.converted_task_id,
        "created_at": demand.created_at.strftime("%d/%m/%Y %H:%M"),
        "can_convert": demand.converted_task_id is None and demand.status in {"aberta", "triagem"},
        "pipeline_column": demand.status if demand.status in {"aberta", "triagem", "convertida", "concluida"} else "aberta",
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
        "period": f"{run.period_start.strftime('%d/%m/%Y')} até {run.period_end.strftime('%d/%m/%Y')}" if run else "-",
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
    projects = db.scalars(
        select(BPOProject).options(selectinload(BPOProject.client), selectinload(BPOProject.responsible_user)).order_by(BPOProject.name.asc())
    ).all()
    templates = db.scalars(
        select(BPOTaskTemplate).where(BPOTaskTemplate.is_active.is_(True)).order_by(BPOTaskTemplate.name.asc())
    ).all()
    return {"clients": clients, "users": users, "task_templates": templates, "projects": projects}


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
            "period": f"{run.period_start.strftime('%d/%m/%Y')} até {run.period_end.strftime('%d/%m/%Y')}",
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
        haystack = " ".join(
            [
                row["trade_name"],
                row["legal_name"],
                row["document"],
                row["segment"],
                row["responsible_name"],
                str(row["contracted_plan"]),
                str(row["team_label"]),
            ]
        ).lower()
        if normalized_search and normalized_search not in haystack:
            continue
        rows.append(row)
    return {
        "client_metrics": [
            {"label": "Carteira", "value": len(rows)},
            {"label": "Com atraso", "value": sum(1 for row in rows if row["overdue_count"])},
            {"label": "Sem responsável", "value": sum(1 for row in rows if row["responsible_name"] == "Sem responsável")},
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
            selectinload(BPOClient.projects).selectinload(BPOProject.responsible_user),
            selectinload(BPOClient.projects).selectinload(BPOProject.tasks),
            selectinload(BPOClient.demands).selectinload(BPODemand.project),
            selectinload(BPOClient.demands).selectinload(BPODemand.responsible_user),
            selectinload(BPOClient.responsible_user),
            selectinload(BPOClient.tasks).selectinload(BPOTask.assigned_user),
            selectinload(BPOClient.tasks).selectinload(BPOTask.project),
            selectinload(BPOClient.tasks).selectinload(BPOTask.time_entries),
            selectinload(BPOClient.tasks).selectinload(BPOTask.events).selectinload(BPOTaskEvent.user),
            selectinload(BPOClient.conciliation_runs).selectinload(BPOConciliationRun.items),
        )
    )
    if not client:
        return None

    tasks = sorted(client.tasks, key=lambda item: (item.completed_at is not None, item.due_date or date.max, item.created_at))
    runs = sorted(client.conciliation_runs, key=lambda item: item.created_at, reverse=True)
    total_seconds = sum(entry.duration_seconds for task in client.tasks for entry in task.time_entries if entry.ended_at)
    open_tasks = [_serialize_task(task) for task in tasks if _task_status(task) != "concluida"]
    recent_demands = [_serialize_demand(item) for item in sorted(client.demands, key=lambda demand: demand.created_at, reverse=True)[:20]]

    return {
        "client": _serialize_client(
            client,
            task_count=sum(1 for task in tasks if _task_status(task) != "concluida"),
            overdue_count=sum(1 for task in tasks if task.due_date and task.due_date < date.today() and _task_status(task) != "concluida"),
            last_run_at=runs[0].created_at if runs else None,
        ),
        "client_metrics": [
            {"label": "Projetos ativos", "value": sum(1 for item in client.projects if item.status == "ativo")},
            {"label": "Tarefas abertas", "value": len(open_tasks)},
            {"label": "Demandas abertas", "value": sum(1 for item in client.demands if item.status in {"aberta", "triagem"})},
            {"label": "Horas gastas", "value": _duration_label(total_seconds)},
        ],
        "contacts": client.contacts,
        "projects": [_serialize_project(project) for project in sorted(client.projects, key=lambda item: item.created_at, reverse=True)],
        "tasks": [_serialize_task(task) for task in tasks[:20]],
        "demands": recent_demands,
        "time_entries": [
            _serialize_time_entry(entry)
            for task in tasks[:20]
            for entry in sorted(task.time_entries, key=lambda item: item.started_at, reverse=True)
        ][:20],
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
                "period": f"{run.period_start.strftime('%d/%m/%Y')} até {run.period_end.strftime('%d/%m/%Y')}",
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


def load_task_manager_overview(db: Session) -> dict[str, object]:
    month_start = date.today().replace(day=1)
    clients = db.scalars(
        select(BPOClient)
        .options(
            selectinload(BPOClient.tasks).selectinload(BPOTask.assigned_user),
            selectinload(BPOClient.demands),
            selectinload(BPOClient.projects),
        )
        .order_by(BPOClient.trade_name.asc(), BPOClient.legal_name.asc())
    ).all()
    projects = db.scalars(
        select(BPOProject).options(selectinload(BPOProject.client), selectinload(BPOProject.responsible_user), selectinload(BPOProject.tasks))
    ).all()
    tasks = db.scalars(
        select(BPOTask)
        .options(selectinload(BPOTask.client), selectinload(BPOTask.project), selectinload(BPOTask.assigned_user), selectinload(BPOTask.events))
        .order_by(BPOTask.created_at.desc())
    ).all()
    demands = db.scalars(
        select(BPODemand)
        .options(selectinload(BPODemand.client), selectinload(BPODemand.project), selectinload(BPODemand.responsible_user))
        .order_by(BPODemand.created_at.desc())
    ).all()
    time_entries = db.scalars(
        select(BPOTaskTimeEntry)
        .options(selectinload(BPOTaskTimeEntry.user), selectinload(BPOTaskTimeEntry.task).selectinload(BPOTask.client))
        .order_by(BPOTaskTimeEntry.started_at.desc())
    ).all()

    active_clients = [client for client in clients if client.status != "inativo"]
    active_projects = [project for project in projects if project.status == "ativo"]
    open_tasks = [task for task in tasks if _task_status(task) != "concluida"]
    open_demands = [item for item in demands if item.status in {"aberta", "triagem"}]
    hours_month = sum(entry.duration_seconds for entry in time_entries if entry.started_at.date() >= month_start and entry.ended_at)
    overdue_tasks = [task for task in open_tasks if _task_status(task) == "atrasada"]
    sla_critical = [task for task in open_tasks if task.due_date and task.due_date <= (date.today() + timedelta(days=1))]

    status_totals: dict[str, int] = defaultdict(int)
    collaborator_totals: dict[str, int] = defaultdict(int)
    client_totals: list[dict[str, object]] = []
    for task in tasks:
        status_totals[_task_status(task)] += 1
    for entry in time_entries:
        if entry.started_at.date() >= month_start:
            collaborator_totals[entry.user.name if entry.user else "Sem responsável"] += entry.duration_seconds
    for client in active_clients[:8]:
        client_tasks = [task for task in client.tasks if task.created_at.date() >= month_start]
        client_demands = [item for item in client.demands if item.created_at.date() >= month_start]
        client_seconds = sum(
            entry.duration_seconds
            for task in client.tasks
            for entry in task.time_entries
            if entry.started_at.date() >= month_start and entry.ended_at
        )
        client_totals.append(
            {
                "client_name": client.trade_name or client.legal_name,
                "hours_label": _duration_label(client_seconds),
                "task_count": len(client_tasks),
                "demand_count": len(client_demands),
            }
        )

    upcoming_tasks = []
    for task in sorted(open_tasks, key=lambda item: item.due_date or date.max)[:6]:
        due_date = task.due_date
        if due_date and due_date < date.today():
            sla_tone = "error"
            sla_label = "Atrasada"
        elif due_date == date.today():
            sla_tone = "warning"
            sla_label = "Hoje"
        else:
            sla_tone = "success"
            sla_label = "Em dia"
        upcoming_tasks.append(
            {
                "id": task.id,
                "title": task.title,
                "client_name": task.client.trade_name or task.client.legal_name,
                "due_date": due_date.strftime("%d/%m/%Y") if due_date else "-",
                "sla_label": sla_label,
                "sla_tone": sla_tone,
                "href": f"/operacoes/gestor-tarefas/tarefasstatus={'atrasada' if sla_tone == 'error' else ''}",
            }
        )

    critical_tasks = [
        _serialize_task(task)
        for task in sorted(
            open_tasks,
            key=lambda item: (
                _task_status(item) != "atrasada",
                item.priority != "alta",
                item.due_date or date.max,
            ),
        )[:6]
    ]

    recent_activities = []
    for task in tasks[:10]:
        for event in sorted(task.events, key=lambda item: item.created_at, reverse=True)[:1]:
            recent_activities.append(
                {
                    "type": "Tarefa",
                    "description": task.title,
                    "reference": f"Cliente: {task.client.trade_name or task.client.legal_name}",
                    "responsible": task.assigned_user.name if task.assigned_user else "Sem responsável",
                    "event_at": event.created_at.strftime("%d/%m/%Y %H:%M"),
                    "event_at_raw": event.created_at,
                }
            )
    for demand in demands[:6]:
        recent_activities.append(
            {
                "type": "Demanda",
                "description": demand.title,
                "reference": f"Cliente: {demand.client.trade_name or demand.client.legal_name}",
                "responsible": demand.responsible_user.name if demand.responsible_user else "Sem responsável",
                "event_at": demand.created_at.strftime("%d/%m/%Y %H:%M"),
                "event_at_raw": demand.created_at,
            }
        )
    recent_activities.sort(key=lambda item: item["event_at_raw"], reverse=True)

    return {
        "manager_metrics": [
            {"label": "Tarefas atrasadas", "value": len(overdue_tasks), "delta": "Acao imediata", "href": "/operacoes/gestor-tarefas/tarefasstatus=atrasada"},
            {"label": "Demandas abertas", "value": len(open_demands), "delta": "Entrada e triagem", "href": "/operacoes/gestor-tarefas/demandasstatus=aberta"},
            {"label": "Projetos ativos", "value": len(active_projects), "delta": "Frentes em execução", "href": "/operacoes/gestor-tarefas/projetos?status=ativo"},
            {"label": "Horas do mês", "value": _duration_label(hours_month), "delta": "Carga operacional", "href": "/operacoes/gestor-tarefas/tempo"},
            {"label": "SLA crítico", "value": len(sla_critical), "delta": "Hoje e atrasadas", "href": "/operacoes/gestor-tarefas/alertas"},
        ],
        "status_rows": [
            {"label": TASK_STATUS_LABELS.get(key, key.title()), "value": value}
            for key, value in sorted(status_totals.items(), key=lambda item: item[1], reverse=True)
        ],
        "collaborator_rows": [
            {"label": label, "value": _duration_label(seconds), "seconds": seconds}
            for label, seconds in sorted(collaborator_totals.items(), key=lambda item: item[1], reverse=True)[:6]
        ],
        "upcoming_tasks": upcoming_tasks,
        "critical_tasks": critical_tasks,
        "recent_demands": [_serialize_demand(item) for item in open_demands[:5]],
        "recent_activities": recent_activities[:8],
        "client_summary": sorted(client_totals, key=lambda item: item["task_count"], reverse=True)[:6],
    }


def load_task_manager_clients(db: Session, *, filters: dict[str, object] | None = None) -> dict[str, object]:
    return load_clients_overview(db, filters=filters)


def load_projects_overview(db: Session, *, filters: dict[str, object] | None = None) -> dict[str, object]:
    filters = filters or {}
    client_id = filters.get("client_id")
    status = str(filters.get("status") or "").strip()
    responsible_user_id = filters.get("responsible_user_id")

    query = select(BPOProject).options(
        selectinload(BPOProject.client),
        selectinload(BPOProject.responsible_user),
        selectinload(BPOProject.tasks),
        selectinload(BPOProject.demands),
    )
    if client_id:
        query = query.where(BPOProject.client_id == client_id)
    if status:
        query = query.where(BPOProject.status == status)
    if responsible_user_id:
        query = query.where(BPOProject.responsible_user_id == responsible_user_id)
    projects = db.scalars(query.order_by(BPOProject.created_at.desc())).all()
    rows = [_serialize_project(item) for item in projects]
    return {
        "project_metrics": [
            {"label": "Projetos", "value": len(rows)},
            {"label": "Ativos", "value": sum(1 for item in rows if item["status"] == "ativo")},
            {"label": "Pausados", "value": sum(1 for item in rows if item["status"] == "pausado")},
            {"label": "Concluídos", "value": sum(1 for item in rows if item["status"] == "concluido")},
        ],
        "project_rows": rows,
        "project_filters": {
            "client_id": client_id,
            "status": status,
            "responsible_user_id": responsible_user_id,
        },
    }


def load_tasks_overview(db: Session, *, filters: dict[str, object] | None = None) -> dict[str, object]:
    filters = filters or {}
    client_id = filters.get("client_id")
    project_id = filters.get("project_id")
    status = str(filters.get("status") or "").strip()
    assigned_user_id = filters.get("assigned_user_id")
    query = select(BPOTask).options(
        selectinload(BPOTask.client),
        selectinload(BPOTask.project),
        selectinload(BPOTask.assigned_user),
        selectinload(BPOTask.time_entries),
    )
    if client_id:
        query = query.where(BPOTask.client_id == client_id)
    if project_id:
        query = query.where(BPOTask.project_id == project_id)
    if status:
        if status == "atrasada":
            query = query.where(BPOTask.status != "concluida", BPOTask.due_date < date.today())
        else:
            query = query.where(BPOTask.status == status)
    if assigned_user_id:
        query = query.where(BPOTask.assigned_user_id == assigned_user_id)
    tasks = db.scalars(query.order_by(BPOTask.due_date.asc().nulls_last(), BPOTask.created_at.desc())).all()
    rows = [_serialize_task(task) for task in tasks]
    board_map = {
        "a_fazer": {"id": "a_fazer", "label": "A fazer", "items": []},
        "em_andamento": {"id": "em_andamento", "label": "Em andamento", "items": []},
        "em_revisao": {"id": "em_revisao", "label": "Em revisão", "items": []},
        "concluidas": {"id": "concluidas", "label": "Concluído", "items": []},
    }
    for item in rows:
        board_map[item["board_column"]]["items"].append(item)
    return {
        "task_metrics": [
            {"label": "Tarefas", "value": len(rows)},
            {"label": "Em execução", "value": sum(1 for item in rows if item["status"] == "em_execucao")},
            {"label": "Em revisão", "value": sum(1 for item in rows if item["status"] == "aguardando_cliente")},
            {"label": "Atrasadas", "value": sum(1 for item in rows if item["status"] == "atrasada")},
        ],
        "task_rows": rows,
        "task_columns": list(board_map.values()),
        "task_filters": {
            "client_id": client_id,
            "project_id": project_id,
            "status": status,
            "assigned_user_id": assigned_user_id,
        },
    }


def load_demands_overview(db: Session, *, filters: dict[str, object] | None = None) -> dict[str, object]:
    filters = filters or {}
    client_id = filters.get("client_id")
    status = str(filters.get("status") or "").strip()
    demand_type = str(filters.get("demand_type") or "").strip()
    query = select(BPODemand).options(
        selectinload(BPODemand.client),
        selectinload(BPODemand.project),
        selectinload(BPODemand.responsible_user),
    )
    if client_id:
        query = query.where(BPODemand.client_id == client_id)
    if status:
        query = query.where(BPODemand.status == status)
    if demand_type:
        query = query.where(BPODemand.demand_type == demand_type)
    demands = db.scalars(query.order_by(BPODemand.created_at.desc())).all()
    rows = [_serialize_demand(item) for item in demands]
    pipeline_map = {
        "aberta": {"id": "aberta", "label": "Entrada", "items": []},
        "triagem": {"id": "triagem", "label": "Triagem", "items": []},
        "convertida": {"id": "convertida", "label": "Convertida", "items": []},
        "concluida": {"id": "concluida", "label": "Concluida", "items": []},
    }
    for item in rows:
        pipeline_map[item["pipeline_column"]]["items"].append(item)
    return {
        "demand_metrics": [
            {"label": "Demandas", "value": len(rows)},
            {"label": "Abertas", "value": sum(1 for item in rows if item["status"] == "aberta")},
            {"label": "Em triagem", "value": sum(1 for item in rows if item["status"] == "triagem")},
            {"label": "Convertidas", "value": sum(1 for item in rows if item["status"] == "convertida")},
        ],
        "demand_rows": rows,
        "demand_columns": list(pipeline_map.values()),
        "demand_filters": {
            "client_id": client_id,
            "status": status,
            "demand_type": demand_type,
        },
    }


def load_time_overview(db: Session) -> dict[str, object]:
    entries = db.scalars(
        select(BPOTaskTimeEntry)
        .options(selectinload(BPOTaskTimeEntry.user), selectinload(BPOTaskTimeEntry.task).selectinload(BPOTask.client))
        .order_by(BPOTaskTimeEntry.started_at.desc())
    ).all()
    active_entries = [_serialize_time_entry(item) for item in entries if item.ended_at is None]
    recent_entries = [_serialize_time_entry(item) for item in entries[:20]]
    per_user: dict[str, int] = defaultdict(int)
    for item in entries:
        if item.ended_at:
            per_user[item.user.name if item.user else "Sem responsável"] += item.duration_seconds
    return {
        "time_metrics": [
            {"label": "Apontamentos", "value": len(entries)},
            {"label": "Em andamento", "value": len(active_entries)},
            {"label": "Horas totais", "value": _duration_label(sum(item.duration_seconds for item in entries if item.ended_at))},
            {"label": "Colaboradores", "value": len(per_user)},
        ],
        "active_time_entries": active_entries,
        "recent_time_entries": recent_entries,
        "time_by_user": [{"label": label, "value": _duration_label(seconds)} for label, seconds in sorted(per_user.items(), key=lambda item: item[1], reverse=True)],
    }


def load_current_time_widget(db: Session, user_id: int | None) -> dict[str, object]:
    if not user_id:
        return {"current_time_entry": None}
    entry = db.scalar(
        select(BPOTaskTimeEntry)
        .where(BPOTaskTimeEntry.user_id == user_id, BPOTaskTimeEntry.ended_at.is_(None))
        .options(selectinload(BPOTaskTimeEntry.task).selectinload(BPOTask.client))
        .order_by(BPOTaskTimeEntry.started_at.desc())
    )
    if not entry:
        return {"current_time_entry": None}
    return {"current_time_entry": _serialize_time_entry(entry)}


def load_routines_overview(db: Session) -> dict[str, object]:
    routines = db.scalars(
        select(BPORecurringRoutine)
        .options(selectinload(BPORecurringRoutine.client), selectinload(BPORecurringRoutine.task_template), selectinload(BPORecurringRoutine.default_assignee))
        .order_by(BPORecurringRoutine.updated_at.desc())
    ).all()
    rows = []
    for item in routines:
        rows.append(
            {
                "id": item.id,
                "client_name": item.client.trade_name or item.client.legal_name,
                "template_name": item.task_template.name if item.task_template else "Sem template",
                "frequency": item.frequency,
                "day_of_month": item.day_of_month or "-",
                "assignee_name": item.default_assignee.name if item.default_assignee else "Sem responsável",
                "status_label": "Ativa" if item.is_active else "Pausada",
            }
        )
    return {
        "routine_metrics": [
            {"label": "Rotinas", "value": len(rows)},
            {"label": "Ativas", "value": sum(1 for item in routines if item.is_active)},
            {"label": "Mensais", "value": sum(1 for item in routines if item.frequency == "monthly")},
            {"label": "Sem responsável", "value": sum(1 for item in routines if item.default_assignee is None)},
        ],
        "routine_rows": rows,
    }


def load_alerts_overview(db: Session) -> dict[str, object]:
    tasks = db.scalars(select(BPOTask).options(selectinload(BPOTask.client), selectinload(BPOTask.assigned_user))).all()
    alerts = []
    for task in tasks:
        if task.status != "concluida" and task.due_date and task.due_date < date.today():
            alerts.append(
                {
                    "type": "Tarefa atrasada",
                    "title": task.title,
                    "client_name": task.client.trade_name or task.client.legal_name,
                    "detail": f"Vencimento em {task.due_date.strftime('%d/%m/%Y')}",
                    "tone": "error",
                }
            )
    clients = db.scalars(select(BPOClient).options(selectinload(BPOClient.tasks))).all()
    for client in clients:
        if client.sla_deadline_day and any(task.status != "concluida" and task.due_date and task.due_date.day > client.sla_deadline_day for task in client.tasks):
            alerts.append(
                {
                    "type": "Cliente fora do SLA",
                    "title": client.trade_name or client.legal_name,
                    "client_name": client.trade_name or client.legal_name,
                    "detail": f"SLA configurado para dia {client.sla_deadline_day}",
                    "tone": "warning",
                }
            )
    user_task_load: dict[str, int] = defaultdict(int)
    for task in tasks:
        if task.status != "concluida" and task.assigned_user:
            user_task_load[task.assigned_user.name] += 1
    for user_name, total in user_task_load.items():
        if total >= 8:
            alerts.append(
                {
                    "type": "Sobrecarga",
                    "title": user_name,
                    "client_name": "Equipe",
                    "detail": f"{total} tarefas abertas sob responsabilidade.",
                    "tone": "warning",
                }
            )
    return {
        "alert_metrics": [
            {"label": "Alertas", "value": len(alerts)},
            {"label": "Críticos", "value": sum(1 for item in alerts if item["tone"] == "error")},
            {"label": "Atenção", "value": sum(1 for item in alerts if item["tone"] == "warning")},
            {"label": "Sobrecarga", "value": sum(1 for item in alerts if item["type"] == "Sobrecarga")},
        ],
        "alert_rows": alerts[:20],
    }


def load_performance_overview(db: Session) -> dict[str, object]:
    month_start = date.today().replace(day=1)
    entries = db.scalars(
        select(BPOTaskTimeEntry)
        .options(selectinload(BPOTaskTimeEntry.user), selectinload(BPOTaskTimeEntry.task).selectinload(BPOTask.client))
    ).all()
    tasks = db.scalars(select(BPOTask).options(selectinload(BPOTask.client), selectinload(BPOTask.assigned_user))).all()
    by_user: dict[str, dict[str, int]] = defaultdict(lambda: {"seconds": 0, "done": 0, "late": 0})
    by_client: dict[str, dict[str, int]] = defaultdict(lambda: {"seconds": 0, "tasks": 0, "sla": 0})
    for entry in entries:
        if entry.ended_at and entry.started_at.date() >= month_start:
            by_user[entry.user.name if entry.user else "Sem responsável"]["seconds"] += entry.duration_seconds
            by_client[entry.task.client.trade_name or entry.task.client.legal_name]["seconds"] += entry.duration_seconds
    for task in tasks:
        if task.created_at.date() >= month_start:
            assignee = task.assigned_user.name if task.assigned_user else "Sem responsável"
            client_name = task.client.trade_name or task.client.legal_name
            by_client[client_name]["tasks"] += 1
            if task.status == "concluida":
                by_user[assignee]["done"] += 1
            if task.due_date and task.due_date < date.today() and task.status != "concluida":
                by_user[assignee]["late"] += 1
            if task.client.sla_deadline_day and task.due_date and task.due_date.day <= task.client.sla_deadline_day:
                by_client[client_name]["sla"] += 1
    return {
        "performance_user_rows": [
            {"label": label, "hours": _duration_label(item["seconds"]), "done": item["done"], "late": item["late"]}
            for label, item in sorted(by_user.items(), key=lambda pair: pair[1]["seconds"], reverse=True)
        ],
        "performance_client_rows": [
            {"label": label, "hours": _duration_label(item["seconds"]), "tasks": item["tasks"], "sla_hits": item["sla"]}
            for label, item in sorted(by_client.items(), key=lambda pair: pair[1]["seconds"], reverse=True)
        ],
    }


def create_task(
    db: Session,
    *,
    client_id: int,
    project_id: int | None,
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
        project_id=project_id,
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
        task.started_at = utcnow()
    if normalized == "concluida":
        task.completed_at = utcnow()
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
    contracted_plan: str,
    sla_deadline_day: int | None,
    team_label: str,
    responsible_user_id: int | None,
    notes: str,
) -> BPOClient:
    client = BPOClient(
        legal_name=legal_name.strip(),
        trade_name=trade_name.strip(),
        document=document.strip(),
        segment=segment.strip(),
        contracted_plan=contracted_plan.strip(),
        sla_deadline_day=sla_deadline_day if sla_deadline_day and sla_deadline_day > 0 else None,
        team_label=team_label.strip(),
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
    contracted_plan: str,
    sla_deadline_day: int | None,
    team_label: str,
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
    client.contracted_plan = contracted_plan.strip()
    client.sla_deadline_day = sla_deadline_day if sla_deadline_day and sla_deadline_day > 0 else None
    client.team_label = team_label.strip()
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


def create_project(
    db: Session,
    *,
    client_id: int,
    name: str,
    project_type: str,
    status: str,
    description: str,
    start_date: date | None,
    end_date: date | None,
    responsible_user_id: int | None,
) -> BPOProject:
    project = BPOProject(
        client_id=client_id,
        name=name.strip(),
        project_type=project_type if project_type in PROJECT_TYPE_LABELS else "rotina_mensal",
        status=status if status in PROJECT_STATUS_LABELS else "ativo",
        description=description.strip(),
        start_date=start_date,
        end_date=end_date,
        responsible_user_id=responsible_user_id,
    )
    db.add(project)
    db.commit()
    return project


def create_demand(
    db: Session,
    *,
    client_id: int,
    project_id: int | None,
    title: str,
    description: str,
    source: str,
    demand_type: str,
    priority: str,
    status: str,
    due_date: date | None,
    responsible_user_id: int | None,
    created_by_user_id: int | None,
) -> BPODemand:
    demand = BPODemand(
        client_id=client_id,
        project_id=project_id,
        title=title.strip(),
        description=description.strip(),
        source=source if source in DEMAND_SOURCE_LABELS else "manual",
        demand_type=demand_type if demand_type in DEMAND_TYPE_LABELS else "operacional",
        priority=priority if priority in PRIORITY_LABELS else "normal",
        status=status if status in DEMAND_STATUS_LABELS else "aberta",
        due_date=due_date,
        responsible_user_id=responsible_user_id,
        created_by_user_id=created_by_user_id,
    )
    db.add(demand)
    db.commit()
    return demand


def convert_demand_to_task(
    db: Session,
    *,
    demand_id: int,
    user_id: int | None,
) -> tuple[BPODemand | None, BPOTask | None]:
    demand = db.scalar(
        select(BPODemand)
        .where(BPODemand.id == demand_id)
        .options(selectinload(BPODemand.client), selectinload(BPODemand.project))
    )
    if not demand:
        return None, None
    if demand.converted_task_id:
        task = db.get(BPOTask, demand.converted_task_id)
        return demand, task
    task = create_task(
        db,
        client_id=demand.client_id,
        project_id=demand.project_id,
        title=demand.title,
        description=demand.description or "Tarefa criada a partir de demanda.",
        created_by_user_id=user_id,
        assigned_user_id=demand.responsible_user_id,
        due_date=demand.due_date,
        priority=demand.priority,
    )
    demand = db.get(BPODemand, demand_id)
    demand.converted_task_id = task.id
    demand.status = "convertida"
    db.commit()
    return demand, task


def start_task_time_entry(
    db: Session,
    *,
    task_id: int,
    user_id: int | None,
) -> BPOTaskTimeEntry | None:
    task = db.get(BPOTask, task_id)
    if not task:
        return None
    existing = db.scalar(
        select(BPOTaskTimeEntry).where(
            BPOTaskTimeEntry.task_id == task_id,
            BPOTaskTimeEntry.user_id == user_id,
            BPOTaskTimeEntry.ended_at.is_(None),
        )
    )
    if existing:
        return existing
    entry = BPOTaskTimeEntry(task_id=task_id, user_id=user_id, started_at=utcnow(), note="Apontamento iniciado.")
    db.add(entry)
    if task.status == "pendente":
        task.status = "em_execucao"
        task.started_at = task.started_at or utcnow()
    db.commit()
    return entry


def stop_task_time_entry(db: Session, *, entry_id: int) -> BPOTaskTimeEntry | None:
    entry = db.scalar(
        select(BPOTaskTimeEntry)
        .where(BPOTaskTimeEntry.id == entry_id)
        .options(selectinload(BPOTaskTimeEntry.task))
    )
    if not entry:
        return None
    if entry.ended_at is None:
        now = utcnow()
        if entry.started_at.tzinfo is None and now.tzinfo is not None:
            now = now.replace(tzinfo=None)
        elif entry.started_at.tzinfo is not None and now.tzinfo is None:
            now = now.replace(tzinfo=entry.started_at.tzinfo)
        entry.ended_at = now
        entry.duration_seconds = max(int((entry.ended_at - entry.started_at).total_seconds()), 0)
    db.commit()
    return entry


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
    title = f"Conciliação {competence_date.strftime('%m/%Y')}"
    return create_task(
        db,
        client_id=client_id,
        project_id=None,
        title=title,
        description="Tarefa gerada automaticamente a partir de uma conciliação sem tarefa prévia.",
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
    project_id: int | None,
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
    task.project_id = project_id
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
        item.detail = f"{preserved}\n\n[{utcnow().strftime('%d/%m/%Y %H:%M UTC')}] {note.strip()}".strip()

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
                detail=str(row.get("Motivo") or "Divergência registrada na conciliação."),
            )
        )

    if task_id:
        update_task_status(
            db,
            task_id=task_id,
            status_value="concluida",
            user_id=user_id,
            note=f"Conciliação concluída para o período {period_start.strftime('%m/%Y')}.",
        )
        run = db.get(BPOConciliationRun, run.id)

    db.commit()
    return run
