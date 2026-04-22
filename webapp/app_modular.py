from __future__ import annotations

import asyncio
import hashlib
import shutil
import tempfile
import time
import unicodedata
import uuid
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, File, Form, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask
from starlette.middleware.sessions import SessionMiddleware

from conciliador.service import ConciliationUserError, run_conciliation

from .bpo_models import BPOClient, BPOConciliationRun, BPOTask
from .finance_models import BPOFinancialBankAccount  # noqa: F401
from .bpo_services import (
    archive_client,
    create_client,
    create_client_contact,
    create_default_task_for_conciliation,
    create_demand,
    create_project,
    create_task,
    convert_demand_to_task,
    delete_task,
    load_client_detail,
    load_client_open_tasks_for_conciliation,
    load_pending_items,
    load_client_reference_lists,
    load_clients_overview,
    load_current_time_widget,
    load_demands_overview,
    load_alerts_overview,
    load_operations_queue,
    load_performance_overview,
    load_projects_overview,
    persist_conciliation_run,
    load_routines_overview,
    load_task_manager_clients,
    load_task_manager_overview,
    load_tasks_overview,
    load_time_overview,
    start_task_time_entry,
    stop_task_time_entry,
    update_client,
    update_pending_item_status,
    update_task,
    update_task_status,
)
from .finance_services import (
    create_financial_bank_account,
    create_financial_category,
    create_financial_cost_center,
    create_financial_payment_method,
    create_financial_supplier,
    load_finance_setup_overview,
    load_finance_setup_reference_lists,
)
from .bootstrap import cleanup_expired_downloads
from .cashflow import (
    build_cashflow_form_state,
    clear_cashflow_caches,
    export_cashflow_workbook,
    load_internal_finance_overview,
    load_cashflow_overview,
    load_cashflow_reference_lists,
    parse_date_input,
    safe_decimal,
)
from .config import settings
from .dependencies import (
    format_currency,
    format_short_date,
    get_db_session,
    render_page,
    require_user,
    set_flash,
    validate_csrf,
)
from .dilmaria.models import DilmariaPopDraft, DilmariaPopRevision, DilmariaPopRun  # noqa: F401
from .lifecycle import app_lifespan
from .routers.auth import router as auth_router
from .routers.dilmaria import router as dilmaria_router
from .routers.health import router as health_router
from .erp import (
    has_permission,
    load_history,
    load_management_reports,
    load_operational_reports,
    load_reference_lists,
)
from .internal_finance_services import (
    create_internal_finance_entries,
    load_internal_finance_detail,
    load_internal_finance_form_prefill,
    parse_schedule_rows,
)
from .models import BankAccount, FinancialCategory, FinancialTransaction, PaymentMethod, Store, User

BASE_DIR = settings.base_dir
DOWNLOADS: dict[str, dict[str, object]] = {}

MAX_UPLOAD_SIZE = 15 * 1024 * 1024
PROCESSING_TIMEOUT_SECONDS = 60
app = FastAPI(title="D3 Hub", lifespan=app_lifespan)
app.state.downloads = DOWNLOADS
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    same_site=settings.session_same_site,
    https_only=settings.session_https_only,
    domain=settings.session_domain,
    max_age=settings.session_max_age_seconds,
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.include_router(auth_router)
app.include_router(health_router)
app.include_router(dilmaria_router)


_get_db = get_db_session
_set_flash = set_flash
_validate_csrf = validate_csrf
_require_user = require_user
_render = render_page


def _cleanup_expired_downloads() -> None:
    cleanup_expired_downloads(DOWNLOADS, ttl_seconds=settings.download_ttl_seconds)


def _cleanup_tempdir(tempdir: str) -> None:
    shutil.rmtree(tempdir, ignore_errors=True)


def _build_download_name() -> str:
    return f"conciliacao_{datetime.now().strftime('%Y-%m-%d_%H%M')}.xlsx"


def _parse_optional_int(value: str | int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    normalized = str(value).strip()
    if not normalized:
        return None
    return int(normalized)


def _normalize_text_input(value: str | None) -> str:
    text = unicodedata.normalize("NFC", str(value or "").strip())
    replacements = {
        "rpido": "rápido",
        "Rapdo": "Rápido",
        "Rpido": "Rápido",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def _parse_required_date(value: str | None, label: str) -> date:
    parsed = parse_date_input(value)
    if not parsed:
        raise ConciliationUserError(f"Informe {label} para registrar a rotina operacional.")
    return parsed


def _normalize_redirect_target(value: str | None, default: str = "/operacoes/dashboard") -> str:
    target = str(value or "").strip()
    if not target.startswith("/"):
        return default
    return target


def _task_manager_tabs(active: str) -> list[dict[str, object]]:
    items = [
        {"id": "visao_geral", "label": "Visão geral", "href": "/operacoes/gestor-tarefas"},
        {"id": "clientes", "label": "Clientes", "href": "/operacoes/gestor-tarefas/clientes"},
        {"id": "projetos", "label": "Projetos", "href": "/operacoes/gestor-tarefas/projetos"},
        {"id": "tarefas", "label": "Tarefas", "href": "/operacoes/gestor-tarefas/tarefas"},
        {"id": "demandas", "label": "Demandas", "href": "/operacoes/gestor-tarefas/demandas"},
        {"id": "tempo", "label": "Tempo", "href": "/operacoes/gestor-tarefas/tempo"},
        {"id": "rotinas", "label": "Rotinas", "href": "/operacoes/gestor-tarefas/rotinas"},
        {"id": "alertas", "label": "Alertas", "href": "/operacoes/gestor-tarefas/alertas"},
        {"id": "performance", "label": "Performance", "href": "/operacoes/gestor-tarefas/performance"},
    ]
    return [{**item, "active": item["id"] == active} for item in items]


def _render_operations_page(
    request: Request,
    user: User,
    db: Session,
    template_name: str,
    active_module: str,
    title: str,
    subtitle: str,
    extra: dict[str, object] | None = None,
):
    payload = {"task_manager_tabs": _task_manager_tabs("visao_geral")}
    payload.update(load_current_time_widget(db, user.id))
    if extra:
        payload.update(extra)
    return _render(request, user, template_name, "operacoes", active_module, title, subtitle, payload)


def _load_recent_conciliation_runs(db: Session, limit: int = 12) -> list[dict[str, object]]:
    runs = db.scalars(
        select(BPOConciliationRun)
        .where(BPOConciliationRun.status == "concluida")
        .order_by(BPOConciliationRun.created_at.desc())
        .limit(limit)
    ).all()
    items = []
    for run in runs:
        client = db.get(BPOClient, run.client_id)
        items.append(
            {
                "id": run.id,
                "client_name": (client.trade_name or client.legal_name) if client else "Cliente removido",
                "period": f"{run.period_start.strftime('%d/%m/%Y')} até {run.period_end.strftime('%d/%m/%Y')}",
                "status": run.status,
                "status_class": "success" if run.status == "concluida" else "warning",
                "divergences": run.total_divergencias,
                "executed_at": run.created_at.strftime("%d/%m/%Y %H:%M"),
            }
        )
    return items


def _render_conciliation_page(
    request: Request,
    user: User,
    db: Session,
    *,
    error: str | None = None,
    submitted_names: dict[str, str] | None = None,
    selected_client_id: int | None = None,
    selected_task_id: int | None = None,
    period_start: str = "",
    period_end: str = "",
):
    refs = load_client_reference_lists(db)
    tasks = load_client_open_tasks_for_conciliation(db, selected_client_id)
    return _render(
        request,
        user,
        "conciliacao.html",
        "operacoes",
        "conciliacao",
        "Conciliação de clientes",
        "Ferramenta operacional para cruzar relatórios, registrar competência e amarrar a execução ao cliente.",
        {
            "history": load_history(db),
            "recent_runs": _load_recent_conciliation_runs(db),
            "submitted_names": submitted_names or {},
            "error": error,
            "selected_client_id": selected_client_id,
            "selected_task_id": selected_task_id,
            "selected_period_start": period_start,
            "selected_period_end": period_end,
            "clients": refs["clients"],
            "open_tasks": tasks,
        },
    )


def _build_query_string(params: dict[str, object]) -> str:
    return urlencode({key: value for key, value in params.items() if value not in (None, "")})


def _finance_settings_url(client_id: int | None = None) -> str:
    query = _build_query_string({"client_id": client_id})
    return f"/operacoes/financeiro/configuracoes{f'{query}' if query else ''}"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


async def _save_upload(upload: UploadFile, target: Path) -> int:
    total_size = 0
    with target.open("wb") as buffer:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > MAX_UPLOAD_SIZE:
                raise ConciliationUserError(f"O arquivo '{upload.filename or target.name}' excede o limite de 15 MB.")
            buffer.write(chunk)
    await upload.close()
    return total_size


def _register_execution(db: Session, **kwargs) -> None:
    from .models import ExecutionLog
    db.add(ExecutionLog(**kwargs))
    db.commit()




@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; script-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'; form-action 'self'"
    return response



@app.get("/gestao/dashboard", response_class=HTMLResponse)
async def gestao_dashboard(request: Request):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        upcoming = db.scalars(
            select(FinancialTransaction)
            .where(FinancialTransaction.status == "previsto", FinancialTransaction.source == "manual")
            .order_by(FinancialTransaction.planned_date.asc())
            .limit(5)
        ).all()
        return _render(
            request,
            user,
            "dashboard.html",
            "gestao",
            "dashboard",
            "D3 Gestão",
            "Gestão interna da própria D3 com visão financeira, cadastros e indicadores administrativos.",
            {
                "history": load_history(db, limit=6),
                "upcoming": upcoming,
                "reference": load_reference_lists(db),
                "dashboard_context": {
                    "kicker": "Gestão interna",
                    "headline": "Controles da própria D3 em um contexto separado",
                    "description": "O financeiro interno da D3 fica organizado em contas a pagar e receber, fluxo de caixa, lançamentos e projeções, sem se misturar com a operação dos clientes.",
                    "module_count": 4,
                    "module_label": "Módulos de gestão",
                    "secondary_label": "Lançamentos previstos",
                    "secondary_value": len(upcoming),
                    "history_title": "Histórico de gestão",
                    "modules": [
                        {"title": "Contas a Pagar / Receber", "description": "Base estrutural dos registros financeiros da empresa.", "href": "/gestao/contas"},
                        {"title": "Fluxo de Caixa", "description": "Visão consolidada do saldo e da saúde financeira ao longo do tempo.", "href": "/gestao/fluxo-caixa"},
                        {"title": "Lançamentos", "description": "Visão operacional e direta para editar e acompanhar os registros.", "href": "/gestao/lancamentos"},
                        {"title": "Projeções", "description": "Estimativas futuras para planejamento e antecipação de caixa.", "href": "/gestao/projecoes"},
                    ],
                },
            },
        )


@app.get("/operacoes/dashboard", response_class=HTMLResponse)
async def operacoes_dashboard(request: Request):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        return _render_operations_page(
            request,
            user,
            db,
            "operations_dashboard.html",
            "dashboard",
            "D3 Operações",
            "Painel executivo da operação, com foco em carga, SLA, produtividade e prioridades.",
            load_task_manager_overview(db),
        )


@app.get("/conciliacao")
async def conciliacao_legacy():
    return RedirectResponse("/operacoes/conciliacao", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/operacoes/conciliacao", response_class=HTMLResponse)
async def conciliacao_page(request: Request, client_id: str | None = Query(default=None)):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        return _render_conciliation_page(request, user, db, selected_client_id=_parse_optional_int(client_id))


@app.get("/operacoes/gestor-tarefas", response_class=HTMLResponse)
async def task_manager_page(request: Request):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        refs = load_client_reference_lists(db)
        return _render_operations_page(
            request,
            user,
            db,
            "task_manager_overview.html",
            "gestor_tarefas",
            "Gestor de tarefas",
            "Centro operacional com clientes, projetos, tarefas, demandas, tempo e alertas.",
            {**load_task_manager_overview(db), **refs, "task_manager_tabs": _task_manager_tabs("visao_geral")},
        )


@app.get("/operacoes/clientes")
async def clients_legacy():
    return RedirectResponse("/operacoes/gestor-tarefas/clientes", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/operacoes/clientes/{client_id}")
async def client_detail_legacy(client_id: int):
    return RedirectResponse(f"/operacoes/gestor-tarefas/clientes/{client_id}", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/operacoes/gestor-tarefas/clientes", response_class=HTMLResponse)
async def task_manager_clients_page(
    request: Request,
    status_value: str | None = Query(default=None, alias="status"),
    responsible_user_id: str | None = Query(default=None),
    search: str | None = Query(default=None),
):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        refs = load_client_reference_lists(db)
        return _render_operations_page(
            request,
            user,
            db,
            "task_manager_clients.html",
            "gestor_tarefas",
            "Clientes",
            "Base contratual e operacional de cada conta atendida pelo time.",
            {
                **load_task_manager_clients(
                    db,
                    filters={
                        "status": (status_value or "").strip(),
                        "responsible_user_id": _parse_optional_int(responsible_user_id),
                        "search": search or "",
                    },
                ),
                **refs,
                "task_manager_tabs": _task_manager_tabs("clientes"),
            },
        )


@app.get("/operacoes/financeiro/configuracoes")
async def finance_settings_legacy():
    return RedirectResponse("/operacoes/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/operacoes/gestor-tarefas/projetos", response_class=HTMLResponse)
async def task_manager_projects_page(
    request: Request,
    client_id: str | None = Query(default=None),
    responsible_user_id: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        refs = load_client_reference_lists(db)
        return _render_operations_page(
            request,
            user,
            db,
            "task_manager_projects.html",
            "gestor_tarefas",
            "Projetos",
            "Projetos ativos por cliente, com responsável, prazo e status.",
            {
                **refs,
                **load_projects_overview(
                    db,
                    filters={
                        "client_id": _parse_optional_int(client_id),
                        "responsible_user_id": _parse_optional_int(responsible_user_id),
                        "status": (status_value or "").strip(),
                    },
                ),
                "task_manager_tabs": _task_manager_tabs("projetos"),
            },
        )


@app.get("/operacoes/gestor-tarefas/clientes/{client_id}", response_class=HTMLResponse)
async def client_detail_page(request: Request, client_id: int):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        detail = load_client_detail(db, client_id)
        if not detail:
            _set_flash(request, "Cliente não encontrado.", "error")
            return RedirectResponse("/operacoes/gestor-tarefas/clientes", status_code=status.HTTP_303_SEE_OTHER)
        refs = load_client_reference_lists(db)
        return _render_operations_page(
            request,
            user,
            db,
            "task_manager_client_detail.html",
            "gestor_tarefas",
            detail["client"]["trade_name"],
            "Visão detalhada do cliente, com projetos, tarefas, demandas, contatos e conciliações.",
            {**detail, **refs, "task_manager_tabs": _task_manager_tabs("clientes")},
        )


@app.get("/operacoes/gestor-tarefas/tarefas", response_class=HTMLResponse)
async def task_manager_tasks_page(
    request: Request,
    client_id: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    project_id: str | None = Query(default=None),
    assigned_user_id: str | None = Query(default=None),
):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        refs = load_client_reference_lists(db)
        return _render_operations_page(
            request,
            user,
            db,
            "task_manager_tasks.html",
            "gestor_tarefas",
            "Tarefas",
            "Execução do time, com status, prioridade, tempo e proximidade de SLA.",
            {
                **refs,
                **load_tasks_overview(
                    db,
                    filters={
                        "client_id": _parse_optional_int(client_id),
                        "project_id": _parse_optional_int(project_id),
                        "status": (status_value or "").strip(),
                        "assigned_user_id": _parse_optional_int(assigned_user_id),
                    },
                ),
                "task_manager_tabs": _task_manager_tabs("tarefas"),
            },
        )


@app.get("/operacoes/pendencias")
async def pending_items_legacy():
    return RedirectResponse("/operacoes/gestor-tarefas/alertas", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/operacoes/gestor-tarefas/demandas", response_class=HTMLResponse)
async def task_manager_demands_page(
    request: Request,
    client_id: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    demand_type: str | None = Query(default=None),
):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        refs = load_client_reference_lists(db)
        return _render_operations_page(
            request,
            user,
            db,
            "task_manager_demands.html",
            "gestor_tarefas",
            "Demandas",
            "Entrada de trabalho vinda do cliente, da equipe ou de canais como WhatsApp e e-mail.",
            {
                **refs,
                **load_demands_overview(
                    db,
                    filters={
                        "client_id": _parse_optional_int(client_id),
                        "status": (status_value or "").strip(),
                        "demand_type": demand_type or "",
                    },
                ),
                "task_manager_tabs": _task_manager_tabs("demandas"),
            },
        )


@app.get("/operacoes/gestor-tarefas/tempo", response_class=HTMLResponse)
async def task_manager_time_page(request: Request):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        return _render_operations_page(
            request,
            user,
            db,
            "task_manager_time.html",
            "gestor_tarefas",
            "Tempo",
            "Leitura das horas registradas e apontamentos em andamento por tarefa.",
            {**load_time_overview(db), "task_manager_tabs": _task_manager_tabs("tempo")},
        )


@app.get("/operacoes/gestor-tarefas/rotinas", response_class=HTMLResponse)
async def task_manager_routines_page(request: Request):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        return _render_operations_page(
            request,
            user,
            db,
            "task_manager_routines.html",
            "gestor_tarefas",
            "Rotinas",
            "Estrutura recorrente que gera previsibilidade e escala para a operação.",
            {**load_routines_overview(db), "task_manager_tabs": _task_manager_tabs("rotinas")},
        )


@app.get("/operacoes/gestor-tarefas/alertas", response_class=HTMLResponse)
async def task_manager_alerts_page(request: Request):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        return _render_operations_page(
            request,
            user,
            db,
            "task_manager_alerts.html",
            "gestor_tarefas",
            "Alertas",
            "Tarefas atrasadas, clientes fora do SLA e sinais de sobrecarga da equipe.",
            {**load_alerts_overview(db), "task_manager_tabs": _task_manager_tabs("alertas")},
        )


@app.get("/operacoes/gestor-tarefas/performance", response_class=HTMLResponse)
async def task_manager_performance_page(request: Request):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        return _render_operations_page(
            request,
            user,
            db,
            "task_manager_performance.html",
            "gestor_tarefas",
            "Performance",
            "Produtividade por colaborador e leitura operacional por cliente.",
            {**load_performance_overview(db), "task_manager_tabs": _task_manager_tabs("performance")},
        )


@app.get("/fluxo-caixa")
async def cashflow_legacy():
    return RedirectResponse("/gestao/fluxo-caixa", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/gestao/financeiro")
async def finance_redirect():
    return RedirectResponse("/gestao/contas", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/gestao/contas", response_class=HTMLResponse)
async def finance_page(
    request: Request,
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    category_id: str | None = Query(default=None),
    store_id: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    account_id: str | None = Query(default=None),
    subcategory: str | None = Query(default=None),
    interested_party: str | None = Query(default=None),
    search: str | None = Query(default=None),
    entry_mode: str | None = Query(default=None),
):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        normalized_category_id = _parse_optional_int(category_id)
        normalized_store_id = _parse_optional_int(store_id)
        normalized_account_id = _parse_optional_int(account_id)
        refs = load_cashflow_reference_lists(db)
        overview = load_internal_finance_overview(
            db,
            filters={
                "date_from": parse_date_input(date_from),
                "date_to": parse_date_input(date_to),
                "category_id": normalized_category_id,
                "store_id": normalized_store_id,
                "status": status_value,
                "account_id": normalized_account_id,
                "subcategory": (subcategory or "").strip(),
                "interested_party": (interested_party or "").strip(),
                "search": (search or "").strip(),
                "entry_mode": (entry_mode or "").strip(),
                "type": "",
                "source": "manual",
            },
            format_currency=format_currency,
            format_short_date=format_short_date,
        )
        export_query = _build_query_string(
            {
                "date_from": date_from or "",
                "date_to": date_to or "",
                "category_id": normalized_category_id,
                "store_id": normalized_store_id,
                "account_id": normalized_account_id,
                "status": status_value or "",
                "subcategory": (subcategory or "").strip(),
                "interested_party": (interested_party or "").strip(),
                "search": (search or "").strip(),
                "entry_mode": (entry_mode or "").strip(),
            }
        )
        export_url = f"/gestao/contas/exportar{f'{export_query}' if export_query else ''}"
        return _render(
            request,
            user,
            "finance_internal.html",
            "gestao",
            "contas",
            "Contas a Pagar e Receber",
            "Base estruturada dos lançamentos financeiros da própria D3.",
            {
                **refs,
                **overview,
                "filters": {
                    "date_from": date_from or "",
                    "date_to": date_to or "",
                    "category_id": normalized_category_id,
                    "store_id": normalized_store_id,
                    "status": status_value or "",
                    "account_id": normalized_account_id,
                    "subcategory": (subcategory or "").strip(),
                    "interested_party": (interested_party or "").strip(),
                    "search": (search or "").strip(),
                    "entry_mode": (entry_mode or "").strip(),
                },
                "page_urls": {
                    "base": "/gestao/contas",
                    "export": export_url,
                    "new_entry": "/gestao/financeiro/novo",
                },
            },
        )


@app.get("/gestao/financeiro/novo", response_class=HTMLResponse)
async def finance_entry_form_page(request: Request, duplicate_id: str | None = Query(default=None)):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        refs = load_cashflow_reference_lists(db)
        form_state = build_cashflow_form_state(db)
        prefill = load_internal_finance_form_prefill(db, _parse_optional_int(duplicate_id))
        return _render(
            request,
            user,
            "finance_internal_form.html",
            "gestao",
            "contas",
            "Novo lançamento financeiro",
            "Cadastre contas a pagar e contas a receber da gestão interna da D3.",
            {
                **refs,
                **form_state,
                **prefill,
            },
        )


@app.get("/gestao/financeiro/lancamentos/{transaction_id}", response_class=HTMLResponse)
async def finance_entry_detail_page(request: Request, transaction_id: int):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        detail = load_internal_finance_detail(
            db,
            transaction_id=transaction_id,
            format_currency=format_currency,
            format_short_date=format_short_date,
        )
        if not detail:
            _set_flash(request, "Lançamento financeiro não encontrado.", "error")
            return RedirectResponse("/gestao/contas", status_code=status.HTTP_303_SEE_OTHER)
        return _render(
            request,
            user,
            "finance_internal_detail.html",
            "gestao",
            "contas",
            "Detalhe do lançamento",
            "Visualize os dados completos e a composição da conta interna.",
            detail,
        )


@app.get("/gestao/fluxo-caixa", response_class=HTMLResponse)
async def cashflow_page(request: Request, date_from: str | None = Query(default=None), date_to: str | None = Query(default=None), category_id: str | None = Query(default=None), store_id: str | None = Query(default=None), status_value: str | None = Query(default=None, alias="status"), account_id: str | None = Query(default=None), movement_type: str | None = Query(default=None, alias="type"), page: int = Query(default=1, ge=1)):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        normalized_category_id = _parse_optional_int(category_id)
        normalized_store_id = _parse_optional_int(store_id)
        normalized_account_id = _parse_optional_int(account_id)
        refs = load_cashflow_reference_lists(db)
        overview = load_cashflow_overview(db, filters={"date_from": parse_date_input(date_from), "date_to": parse_date_input(date_to), "category_id": normalized_category_id, "store_id": normalized_store_id, "status": status_value, "account_id": normalized_account_id, "type": movement_type, "source": "manual"}, format_currency=format_currency, format_short_date=format_short_date, page=page)
        form_state = build_cashflow_form_state(db)
        export_query = _build_query_string({"date_from": date_from or "", "date_to": date_to or "", "category_id": normalized_category_id, "store_id": normalized_store_id, "account_id": normalized_account_id, "status": status_value or "", "type": movement_type or ""})
        export_url = f"/gestao/fluxo-caixa/exportar{f'{export_query}' if export_query else ''}"
        return _render(request, user, "cashflow.html", "gestao", "fluxo_caixa", "Fluxo de Caixa", "Visão consolidada de tudo que entra e sai da D3 ao longo do tempo.", {**refs, **overview, **form_state, "filters": {"date_from": date_from or "", "date_to": date_to or "", "category_id": normalized_category_id, "store_id": normalized_store_id, "status": status_value or "", "account_id": normalized_account_id, "type": movement_type or ""}, "page_urls": {"base": "/gestao/fluxo-caixa", "export": export_url, "new_entry": "/gestao/financeiro/novo"}})


@app.get("/gestao/lancamentos", response_class=HTMLResponse)
async def internal_entries_page(
    request: Request,
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    category_id: str | None = Query(default=None),
    store_id: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    account_id: str | None = Query(default=None),
    movement_type: str | None = Query(default=None, alias="type"),
    subcategory: str | None = Query(default=None),
    interested_party: str | None = Query(default=None),
    search: str | None = Query(default=None),
    entry_mode: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        normalized_category_id = _parse_optional_int(category_id)
        normalized_store_id = _parse_optional_int(store_id)
        normalized_account_id = _parse_optional_int(account_id)
        refs = load_cashflow_reference_lists(db)
        overview = load_cashflow_overview(
            db,
            filters={
                "date_from": parse_date_input(date_from),
                "date_to": parse_date_input(date_to),
                "category_id": normalized_category_id,
                "store_id": normalized_store_id,
                "status": status_value,
                "account_id": normalized_account_id,
                "subcategory": (subcategory or "").strip(),
                "interested_party": (interested_party or "").strip(),
                "search": (search or "").strip(),
                "entry_mode": (entry_mode or "").strip(),
                "type": movement_type,
                "source": "manual",
            },
            format_currency=format_currency,
            format_short_date=format_short_date,
            page=page,
            page_size=50,
        )
        export_query = _build_query_string(
            {
                "date_from": date_from or "",
                "date_to": date_to or "",
                "category_id": normalized_category_id,
                "store_id": normalized_store_id,
                "account_id": normalized_account_id,
                "status": status_value or "",
                "type": movement_type or "",
                "subcategory": (subcategory or "").strip(),
                "interested_party": (interested_party or "").strip(),
                "search": (search or "").strip(),
                "entry_mode": (entry_mode or "").strip(),
            }
        )
        export_url = f"/gestao/lancamentos/exportar{f'{export_query}' if export_query else ''}"
        return _render(
            request,
            user,
            "finance_entries.html",
            "gestao",
            "lancamentos",
            "Lançamentos",
            "Visão operacional e direta de todas as entradas e saídas da D3.",
            {
                **refs,
                **overview,
                "filters": {
                    "date_from": date_from or "",
                    "date_to": date_to or "",
                    "category_id": normalized_category_id,
                    "store_id": normalized_store_id,
                    "status": status_value or "",
                    "account_id": normalized_account_id,
                    "subcategory": (subcategory or "").strip(),
                    "interested_party": (interested_party or "").strip(),
                    "search": (search or "").strip(),
                    "entry_mode": (entry_mode or "").strip(),
                    "type": movement_type or "",
                },
                "page_urls": {
                    "base": "/gestao/lancamentos",
                    "export": export_url,
                    "new_entry": "/gestao/financeiro/novo",
                },
                "module_meta": {
                    "kicker": "Operacional",
                    "title": "Lançamentos",
                    "description": "Lista direta de todos os registros financeiros para abrir, duplicar e controlar rapidamente.",
                    "empty_state": "Nenhum lançamento encontrado com os filtros atuais.",
                },
            },
        )


@app.get("/gestao/projecoes", response_class=HTMLResponse)
async def internal_projections_page(
    request: Request,
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    category_id: str | None = Query(default=None),
    store_id: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    account_id: str | None = Query(default=None),
    movement_type: str | None = Query(default=None, alias="type"),
    subcategory: str | None = Query(default=None),
    interested_party: str | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        normalized_category_id = _parse_optional_int(category_id)
        normalized_store_id = _parse_optional_int(store_id)
        normalized_account_id = _parse_optional_int(account_id)
        refs = load_cashflow_reference_lists(db)
        overview = load_cashflow_overview(
            db,
            filters={
                "date_from": parse_date_input(date_from),
                "date_to": parse_date_input(date_to),
                "category_id": normalized_category_id,
                "store_id": normalized_store_id,
                "status": status_value,
                "account_id": normalized_account_id,
                "subcategory": (subcategory or "").strip(),
                "interested_party": (interested_party or "").strip(),
                "search": (search or "").strip(),
                "entry_mode": "projecao",
                "type": movement_type,
                "source": "manual",
            },
            format_currency=format_currency,
            format_short_date=format_short_date,
            page=page,
            page_size=50,
        )
        export_query = _build_query_string(
            {
                "date_from": date_from or "",
                "date_to": date_to or "",
                "category_id": normalized_category_id,
                "store_id": normalized_store_id,
                "account_id": normalized_account_id,
                "status": status_value or "",
                "type": movement_type or "",
                "subcategory": (subcategory or "").strip(),
                "interested_party": (interested_party or "").strip(),
                "search": (search or "").strip(),
            }
        )
        export_url = f"/gestao/projecoes/exportar{f'{export_query}' if export_query else ''}"
        return _render(
            request,
            user,
            "finance_entries.html",
            "gestao",
            "projecoes",
            "Projeções",
            "Estimativas financeiras futuras para planejamento e antecipação de caixa.",
            {
                **refs,
                **overview,
                "filters": {
                    "date_from": date_from or "",
                    "date_to": date_to or "",
                    "category_id": normalized_category_id,
                    "store_id": normalized_store_id,
                    "status": status_value or "",
                    "account_id": normalized_account_id,
                    "subcategory": (subcategory or "").strip(),
                    "interested_party": (interested_party or "").strip(),
                    "search": (search or "").strip(),
                    "entry_mode": "projecao",
                    "type": movement_type or "",
                },
                "page_urls": {
                    "base": "/gestao/projecoes",
                    "export": export_url,
                    "new_entry": "/gestao/financeiro/novo",
                },
                "module_meta": {
                    "kicker": "Planejamento",
                    "title": "Projeções",
                    "description": "Registros futuros ainda não realizados, usados para simular o comportamento do caixa.",
                    "empty_state": "Nenhuma projecao encontrada com os filtros atuais.",
                    "fixed_entry_mode": True,
                },
            },
        )


@app.get("/gestao/contas/exportar")
@app.get("/gestao/financeiro/exportar")
@app.get("/gestao/fluxo-caixa/exportar")
@app.get("/gestao/lancamentos/exportar")
@app.get("/gestao/projecoes/exportar")
async def export_cashflow(
    request: Request,
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    category_id: str | None = Query(default=None),
    store_id: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    account_id: str | None = Query(default=None),
    movement_type: str | None = Query(default=None, alias="type"),
    subcategory: str | None = Query(default=None),
    interested_party: str | None = Query(default=None),
    search: str | None = Query(default=None),
    entry_mode: str | None = Query(default=None),
):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        path = request.url.path
        forced_entry_mode = "projecao" if path.endswith("/projecoes/exportar") else (entry_mode or "").strip()
        filters = {
            "date_from": parse_date_input(date_from),
            "date_to": parse_date_input(date_to),
            "category_id": _parse_optional_int(category_id),
            "store_id": _parse_optional_int(store_id),
            "status": status_value,
            "account_id": _parse_optional_int(account_id),
            "subcategory": (subcategory or "").strip(),
            "interested_party": (interested_party or "").strip(),
            "search": (search or "").strip(),
            "entry_mode": forced_entry_mode,
            "type": movement_type,
            "source": "manual",
        }
        workbook = export_cashflow_workbook(db, filters=filters, generated_by=user.name)
        filename = f"fluxo_caixa_d3_{datetime.now().strftime('%Y-%m-%d_%H%M')}.xlsx"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return StreamingResponse(workbook, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers=headers)


@app.get("/cadastros")
async def cadastros_legacy():
    return RedirectResponse("/gestao/cadastros", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/gestao/cadastros", response_class=HTMLResponse)
async def cadastros_page(request: Request):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        return _render(request, user, "cadastros.html", "gestao", "cadastros", "Cadastros internos", "Estruturas da própria D3 para fluxo de caixa, relatórios e parametrização financeira.", load_reference_lists(db))


@app.get("/gestao/relatorios", response_class=HTMLResponse)
async def management_reports_page(request: Request):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        return _render(
            request,
            user,
            "reports.html",
            "gestao",
            "relatorios",
            "Relatórios de gestão",
            "Leitura financeira da operação interna.",
            load_management_reports(db),
        )


@app.get("/operacoes/relatorios", response_class=HTMLResponse)
async def operational_reports_page(request: Request):
    return RedirectResponse("/operacoes/gestor-tarefas/performance", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/relatorios")
async def reports_selector(request: Request):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        return _render(
            request,
            user,
            "reports_selector.html",
            "hub",
            "relatorios",
            "Relatórios",
            "Escolha a área antes de abrir os relatórios.",
            {},
        )




@app.post("/operacoes/clientes")
async def create_bpo_client(
    request: Request,
    legal_name: str = Form(...),
    trade_name: str = Form(default=""),
    document: str = Form(default=""),
    segment: str = Form(default=""),
    contracted_plan: str = Form(default=""),
    sla_deadline_day: str | None = Form(default=None),
    team_label: str = Form(default=""),
    responsible_user_id: str | None = Form(default=None),
    notes: str = Form(default=""),
):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user or not has_permission(user, "edit"):
            return RedirectResponse("/operacoes/gestor-tarefas/clientes", status_code=status.HTTP_303_SEE_OTHER)
        await _validate_csrf(request)
        create_client(
            db,
            legal_name=legal_name,
            trade_name=trade_name or legal_name,
            document=document,
            segment=segment,
            contracted_plan=contracted_plan,
            sla_deadline_day=_parse_optional_int(sla_deadline_day),
            team_label=team_label,
            responsible_user_id=_parse_optional_int(responsible_user_id),
            notes=notes,
        )
        _set_flash(request, "Cliente da carteira cadastrado.", "success")
        return RedirectResponse("/operacoes/gestor-tarefas/clientes", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/operacoes/clientes/{client_id}/atualizar")
async def update_bpo_client(
    request: Request,
    client_id: int,
    legal_name: str = Form(...),
    trade_name: str = Form(default=""),
    document: str = Form(default=""),
    segment: str = Form(default=""),
    contracted_plan: str = Form(default=""),
    sla_deadline_day: str | None = Form(default=None),
    team_label: str = Form(default=""),
    responsible_user_id: str | None = Form(default=None),
    notes: str = Form(default=""),
    status_value: str = Form(default="ativo", alias="status"),
):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user or not has_permission(user, "edit"):
            return RedirectResponse(f"/operacoes/gestor-tarefas/clientes/{client_id}", status_code=status.HTTP_303_SEE_OTHER)
        await _validate_csrf(request)
        client = update_client(
            db,
            client_id=client_id,
            legal_name=legal_name,
            trade_name=trade_name,
            document=document,
            segment=segment,
            contracted_plan=contracted_plan,
            sla_deadline_day=_parse_optional_int(sla_deadline_day),
            team_label=team_label,
            responsible_user_id=_parse_optional_int(responsible_user_id),
            notes=notes,
            status=status_value,
        )
        if not client:
            _set_flash(request, "Cliente não encontrado.", "error")
            return RedirectResponse("/operacoes/gestor-tarefas/clientes", status_code=status.HTTP_303_SEE_OTHER)
        _set_flash(request, "Cliente atualizado.", "success")
        return RedirectResponse(f"/operacoes/gestor-tarefas/clientes/{client_id}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/operacoes/clientes/{client_id}/arquivar")
async def archive_bpo_client(request: Request, client_id: int):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user or not has_permission(user, "edit"):
            return RedirectResponse(f"/operacoes/gestor-tarefas/clientes/{client_id}", status_code=status.HTTP_303_SEE_OTHER)
        await _validate_csrf(request)
        client = archive_client(db, client_id=client_id)
        if not client:
            _set_flash(request, "Cliente não encontrado.", "error")
            return RedirectResponse("/operacoes/gestor-tarefas/clientes", status_code=status.HTTP_303_SEE_OTHER)
        _set_flash(request, "Cliente arquivado na carteira.", "success")
        return RedirectResponse("/operacoes/gestor-tarefas/clientes", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/operacoes/gestor-tarefas/projetos")
async def create_bpo_project(
    request: Request,
    client_id: str = Form(...),
    name: str = Form(...),
    project_type: str = Form(default="rotina_mensal"),
    status_value: str = Form(default="ativo", alias="status"),
    description: str = Form(default=""),
    start_date: str | None = Form(default=None),
    end_date: str | None = Form(default=None),
    responsible_user_id: str | None = Form(default=None),
):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user or not has_permission(user, "edit"):
            return RedirectResponse("/operacoes/gestor-tarefas/projetos", status_code=status.HTTP_303_SEE_OTHER)
        await _validate_csrf(request)
        create_project(
            db,
            client_id=int(client_id),
            name=name,
            project_type=project_type,
            status=status_value,
            description=description,
            start_date=parse_date_input(start_date),
            end_date=parse_date_input(end_date),
            responsible_user_id=_parse_optional_int(responsible_user_id),
        )
        _set_flash(request, "Projeto criado no gestor de tarefas.", "success")
        return RedirectResponse("/operacoes/gestor-tarefas/projetos", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/operacoes/gestor-tarefas/demandas")
async def create_bpo_demand(
    request: Request,
    client_id: str = Form(...),
    project_id: str | None = Form(default=None),
    title: str = Form(...),
    description: str = Form(default=""),
    source: str = Form(default="manual"),
    demand_type: str = Form(default="operacional"),
    priority: str = Form(default="normal"),
    status_value: str = Form(default="aberta", alias="status"),
    due_date: str | None = Form(default=None),
    responsible_user_id: str | None = Form(default=None),
):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user or not has_permission(user, "edit"):
            return RedirectResponse("/operacoes/gestor-tarefas/demandas", status_code=status.HTTP_303_SEE_OTHER)
        await _validate_csrf(request)
        create_demand(
            db,
            client_id=int(client_id),
            project_id=_parse_optional_int(project_id),
            title=title,
            description=description,
            source=source,
            demand_type=demand_type,
            priority=priority,
            status=status_value,
            due_date=parse_date_input(due_date),
            responsible_user_id=_parse_optional_int(responsible_user_id),
            created_by_user_id=user.id,
        )
        _set_flash(request, "Demanda registrada.", "success")
        return RedirectResponse("/operacoes/gestor-tarefas/demandas", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/operacoes/gestor-tarefas/demandas/{demand_id}/converter")
async def convert_bpo_demand(request: Request, demand_id: int):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user or not has_permission(user, "edit"):
            return RedirectResponse("/operacoes/gestor-tarefas/demandas", status_code=status.HTTP_303_SEE_OTHER)
        await _validate_csrf(request)
        demand, task = convert_demand_to_task(db, demand_id=demand_id, user_id=user.id)
        if not demand or not task:
            _set_flash(request, "Demanda não encontrada.", "error")
        else:
            _set_flash(request, "Demanda convertida em tarefa.", "success")
        return RedirectResponse("/operacoes/gestor-tarefas/demandas", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/operacoes/financeiro/contas-bancarias")
async def create_financial_bank_account_entry(
    request: Request,
    client_id: str = Form(...),
    bank_name: str = Form(...),
    account_name: str = Form(...),
    agency: str = Form(default=""),
    account_number: str = Form(default=""),
    pix_key: str = Form(default=""),
    initial_balance: str = Form(default="0"),
):
    selected_client_id = _parse_optional_int(client_id)
    target_url = _finance_settings_url(selected_client_id)
    with _get_db() as db:
        user = _require_user(request, db)
        if not user or not has_permission(user, "edit"):
            return RedirectResponse(target_url, status_code=status.HTTP_303_SEE_OTHER)
        await _validate_csrf(request)
        try:
            if selected_client_id is None:
                raise ValueError("Selecione um cliente para cadastrar a conta bancaria.")
            create_financial_bank_account(
                db,
                client_id=selected_client_id,
                bank_name=bank_name,
                account_name=account_name,
                agency=agency,
                account_number=account_number,
                pix_key=pix_key,
                initial_balance=safe_decimal(initial_balance),
            )
            _set_flash(request, "Conta bancaria cadastrada.", "success")
        except ValueError as exc:
            _set_flash(request, str(exc), "error")
        return RedirectResponse(target_url, status_code=status.HTTP_303_SEE_OTHER)


@app.post("/operacoes/financeiro/categorias")
async def create_financial_category_entry(
    request: Request,
    client_id: str = Form(...),
    name: str = Form(...),
    kind: str = Form(default="saida"),
    parent_id: str | None = Form(default=None),
):
    selected_client_id = _parse_optional_int(client_id)
    target_url = _finance_settings_url(selected_client_id)
    with _get_db() as db:
        user = _require_user(request, db)
        if not user or not has_permission(user, "edit"):
            return RedirectResponse(target_url, status_code=status.HTTP_303_SEE_OTHER)
        await _validate_csrf(request)
        try:
            if selected_client_id is None:
                raise ValueError("Selecione um cliente para cadastrar a categoria.")
            create_financial_category(
                db,
                client_id=selected_client_id,
                name=name,
                kind=kind,
                parent_id=_parse_optional_int(parent_id),
            )
            _set_flash(request, "Categoria financeira cadastrada.", "success")
        except ValueError as exc:
            _set_flash(request, str(exc), "error")
        return RedirectResponse(target_url, status_code=status.HTTP_303_SEE_OTHER)


@app.post("/operacoes/financeiro/centros-custo")
async def create_financial_cost_center_entry(
    request: Request,
    client_id: str = Form(...),
    name: str = Form(...),
):
    selected_client_id = _parse_optional_int(client_id)
    target_url = _finance_settings_url(selected_client_id)
    with _get_db() as db:
        user = _require_user(request, db)
        if not user or not has_permission(user, "edit"):
            return RedirectResponse(target_url, status_code=status.HTTP_303_SEE_OTHER)
        await _validate_csrf(request)
        try:
            if selected_client_id is None:
                raise ValueError("Selecione um cliente para cadastrar o centro de custo.")
            create_financial_cost_center(db, client_id=selected_client_id, name=name)
            _set_flash(request, "Centro de custo cadastrado.", "success")
        except ValueError as exc:
            _set_flash(request, str(exc), "error")
        return RedirectResponse(target_url, status_code=status.HTTP_303_SEE_OTHER)


@app.post("/operacoes/financeiro/fornecedores")
async def create_financial_supplier_entry(
    request: Request,
    client_id: str = Form(...),
    name: str = Form(...),
    document: str = Form(default=""),
    email: str = Form(default=""),
    phone: str = Form(default=""),
):
    selected_client_id = _parse_optional_int(client_id)
    target_url = _finance_settings_url(selected_client_id)
    with _get_db() as db:
        user = _require_user(request, db)
        if not user or not has_permission(user, "edit"):
            return RedirectResponse(target_url, status_code=status.HTTP_303_SEE_OTHER)
        await _validate_csrf(request)
        try:
            if selected_client_id is None:
                raise ValueError("Selecione um cliente para cadastrar o fornecedor.")
            create_financial_supplier(
                db,
                client_id=selected_client_id,
                name=name,
                document=document,
                email=email,
                phone=phone,
            )
            _set_flash(request, "Fornecedor cadastrado.", "success")
        except ValueError as exc:
            _set_flash(request, str(exc), "error")
        return RedirectResponse(target_url, status_code=status.HTTP_303_SEE_OTHER)


@app.post("/operacoes/financeiro/formas-pagamento")
async def create_financial_payment_method_entry(
    request: Request,
    client_id: str = Form(...),
    name: str = Form(...),
):
    selected_client_id = _parse_optional_int(client_id)
    target_url = _finance_settings_url(selected_client_id)
    with _get_db() as db:
        user = _require_user(request, db)
        if not user or not has_permission(user, "edit"):
            return RedirectResponse(target_url, status_code=status.HTTP_303_SEE_OTHER)
        await _validate_csrf(request)
        try:
            if selected_client_id is None:
                raise ValueError("Selecione um cliente para cadastrar a forma de pagamento.")
            create_financial_payment_method(db, client_id=selected_client_id, name=name)
            _set_flash(request, "Forma de pagamento cadastrada.", "success")
        except ValueError as exc:
            _set_flash(request, str(exc), "error")
        return RedirectResponse(target_url, status_code=status.HTTP_303_SEE_OTHER)


@app.post("/operacoes/clientes/{client_id}/contatos")
async def create_bpo_contact(
    request: Request,
    client_id: int,
    name: str = Form(...),
    email: str = Form(default=""),
    phone: str = Form(default=""),
    role: str = Form(default=""),
    is_primary: str | None = Form(default=None),
):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user or not has_permission(user, "edit"):
            return RedirectResponse(f"/operacoes/gestor-tarefas/clientes/{client_id}", status_code=status.HTTP_303_SEE_OTHER)
        await _validate_csrf(request)
        create_client_contact(
            db,
            client_id=client_id,
            name=name,
            email=email,
            phone=phone,
            role=role,
            is_primary=is_primary == "on",
        )
        _set_flash(request, "Contato salvo no cliente.", "success")
        return RedirectResponse(f"/operacoes/gestor-tarefas/clientes/{client_id}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/operacoes/clientes/{client_id}/tarefas")
async def create_bpo_task(
    request: Request,
    client_id: int,
    project_id: str | None = Form(default=None),
    title: str = Form(...),
    description: str = Form(default=""),
    task_template_id: str | None = Form(default=None),
    competence_date: str | None = Form(default=None),
    due_date: str | None = Form(default=None),
    assigned_user_id: str | None = Form(default=None),
    priority: str = Form(default="normal"),
):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user or not has_permission(user, "edit"):
            return RedirectResponse(f"/operacoes/gestor-tarefas/clientes/{client_id}", status_code=status.HTTP_303_SEE_OTHER)
        await _validate_csrf(request)
        create_task(
            db,
            client_id=client_id,
            project_id=_parse_optional_int(project_id),
            title=title,
            description=description,
            created_by_user_id=user.id,
            assigned_user_id=_parse_optional_int(assigned_user_id),
            task_template_id=_parse_optional_int(task_template_id),
            competence_date=parse_date_input(competence_date),
            due_date=parse_date_input(due_date),
            priority=priority,
        )
        _set_flash(request, "Tarefa operacional criada.", "success")
        return RedirectResponse(f"/operacoes/gestor-tarefas/clientes/{client_id}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/operacoes/tarefas/{task_id}/atualizar")
async def update_bpo_task(
    request: Request,
    task_id: int,
    redirect_to: str = Form(default="/operacoes/dashboard"),
    project_id: str | None = Form(default=None),
    title: str = Form(...),
    description: str = Form(default=""),
    competence_date: str | None = Form(default=None),
    due_date: str | None = Form(default=None),
    assigned_user_id: str | None = Form(default=None),
    priority: str = Form(default="normal"),
):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user or not has_permission(user, "edit"):
            return RedirectResponse(_normalize_redirect_target(redirect_to), status_code=status.HTTP_303_SEE_OTHER)
        await _validate_csrf(request)
        task = update_task(
            db,
            task_id=task_id,
            project_id=_parse_optional_int(project_id),
            title=title,
            description=description,
            assigned_user_id=_parse_optional_int(assigned_user_id),
            competence_date=parse_date_input(competence_date),
            due_date=parse_date_input(due_date),
            priority=priority,
        )
        if not task:
            _set_flash(request, "Tarefa não encontrada.", "error")
        else:
            _set_flash(request, "Tarefa atualizada.", "success")
        return RedirectResponse(_normalize_redirect_target(redirect_to), status_code=status.HTTP_303_SEE_OTHER)


@app.post("/operacoes/tarefas/{task_id}/status")
async def change_bpo_task_status(
    request: Request,
    task_id: int,
    status_value: str = Form(..., alias="status"),
    redirect_to: str = Form(default="/operacoes/dashboard"),
    note: str = Form(default=""),
):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user or not has_permission(user, "edit"):
            return RedirectResponse(_normalize_redirect_target(redirect_to), status_code=status.HTTP_303_SEE_OTHER)
        await _validate_csrf(request)
        task = update_task_status(db, task_id=task_id, status_value=status_value, user_id=user.id, note=note)
        if not task:
            _set_flash(request, "Tarefa não encontrada.", "error")
        else:
            _set_flash(request, "Status da tarefa atualizado.", "success")
        return RedirectResponse(_normalize_redirect_target(redirect_to), status_code=status.HTTP_303_SEE_OTHER)


@app.post("/operacoes/tarefas/{task_id}/tempo/iniciar")
async def start_bpo_task_time(
    request: Request,
    task_id: int,
    redirect_to: str = Form(default="/operacoes/gestor-tarefas/tarefas"),
):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user or not has_permission(user, "edit"):
            return RedirectResponse(_normalize_redirect_target(redirect_to, "/operacoes/gestor-tarefas/tarefas"), status_code=status.HTTP_303_SEE_OTHER)
        await _validate_csrf(request)
        entry = start_task_time_entry(db, task_id=task_id, user_id=user.id)
        if not entry:
            _set_flash(request, "Tarefa não encontrada para iniciar apontamento.", "error")
        else:
            _set_flash(request, "Tempo iniciado.", "success")
        return RedirectResponse(_normalize_redirect_target(redirect_to, "/operacoes/gestor-tarefas/tarefas"), status_code=status.HTTP_303_SEE_OTHER)


@app.post("/operacoes/tempo/{entry_id}/pausar")
async def stop_bpo_task_time(
    request: Request,
    entry_id: int,
    redirect_to: str = Form(default="/operacoes/gestor-tarefas/tempo"),
):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user or not has_permission(user, "edit"):
            return RedirectResponse(_normalize_redirect_target(redirect_to, "/operacoes/gestor-tarefas/tempo"), status_code=status.HTTP_303_SEE_OTHER)
        await _validate_csrf(request)
        entry = stop_task_time_entry(db, entry_id=entry_id)
        if not entry:
            _set_flash(request, "Apontamento não encontrado.", "error")
        else:
            _set_flash(request, "Tempo pausado.", "success")
        return RedirectResponse(_normalize_redirect_target(redirect_to, "/operacoes/gestor-tarefas/tempo"), status_code=status.HTTP_303_SEE_OTHER)


@app.post("/operacoes/tarefas/{task_id}/excluir")
async def remove_bpo_task(
    request: Request,
    task_id: int,
    redirect_to: str = Form(default="/operacoes/dashboard"),
):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user or not has_permission(user, "edit"):
            return RedirectResponse(_normalize_redirect_target(redirect_to), status_code=status.HTTP_303_SEE_OTHER)
        await _validate_csrf(request)
        success, message = delete_task(db, task_id=task_id)
        _set_flash(request, message, "success" if success else "error")
        return RedirectResponse(_normalize_redirect_target(redirect_to), status_code=status.HTTP_303_SEE_OTHER)


@app.post("/operacoes/pendencias/{item_id}/status")
async def change_pending_item_status(
    request: Request,
    item_id: int,
    status_value: str = Form(..., alias="status"),
    redirect_to: str = Form(default="/operacoes/pendencias"),
    note: str = Form(default=""),
):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user or not has_permission(user, "edit"):
            return RedirectResponse(_normalize_redirect_target(redirect_to, "/operacoes/pendencias"), status_code=status.HTTP_303_SEE_OTHER)
        await _validate_csrf(request)
        item = update_pending_item_status(db, item_id=item_id, status_value=status_value, user_id=user.id, note=note)
        if not item:
            _set_flash(request, "Pendência não encontrada.", "error")
        else:
            _set_flash(request, "Pendência atualizada.", "success")
        return RedirectResponse(_normalize_redirect_target(redirect_to, "/operacoes/pendencias"), status_code=status.HTTP_303_SEE_OTHER)


@app.post("/conciliar")
async def conciliar(
    request: Request,
    client_id: str = Form(...),
    task_id: str | None = Form(default=None),
    period_start: str = Form(...),
    period_end: str = Form(...),
    vendas: UploadFile = File(...),
    recebimentos: UploadFile = File(...),
):
    _cleanup_expired_downloads()
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        if not has_permission(user, "upload"):
            _set_flash(request, "Seu perfil não possui permissão para enviar arquivos.", "error")
            return RedirectResponse("/operacoes/conciliacao", status_code=status.HTTP_303_SEE_OTHER)
        try:
            await _validate_csrf(request)
        except ConciliationUserError as exc:
            return _render_conciliation_page(
                request,
                user,
                db,
                error=str(exc),
                selected_client_id=_parse_optional_int(client_id),
                selected_task_id=_parse_optional_int(task_id),
                period_start=period_start,
                period_end=period_end,
            )

        selected_client_id = _parse_optional_int(client_id)
        selected_task_id = _parse_optional_int(task_id)
        try:
            selected_period_start = _parse_required_date(period_start, "a data inicial")
            selected_period_end = _parse_required_date(period_end, "a data final")
        except ConciliationUserError as exc:
            return _render_conciliation_page(
                request,
                user,
                db,
                error=str(exc),
                selected_client_id=selected_client_id,
                selected_task_id=selected_task_id,
                period_start=period_start,
                period_end=period_end,
            )
        if selected_period_end < selected_period_start:
            return _render_conciliation_page(
                request,
                user,
                db,
                error="O período final não pode ser anterior ao período inicial.",
                selected_client_id=selected_client_id,
                selected_task_id=selected_task_id,
                period_start=period_start,
                period_end=period_end,
            )
        client = db.get(BPOClient, selected_client_id) if selected_client_id else None
        if not client:
            return _render_conciliation_page(
                request,
                user,
                db,
                error="Selecione um cliente válido antes de processar a conciliação.",
                selected_client_id=selected_client_id,
                selected_task_id=selected_task_id,
                period_start=period_start,
                period_end=period_end,
            )
        if selected_task_id:
            linked_task = db.get(BPOTask, selected_task_id)
            if not linked_task or linked_task.client_id != client.id:
                return _render_conciliation_page(
                    request,
                    user,
                    db,
                    error="A tarefa escolhida não pertence ao cliente selecionado.",
                    selected_client_id=selected_client_id,
                    selected_task_id=selected_task_id,
                    period_start=period_start,
                    period_end=period_end,
                )

        filenames = {"vendas": vendas.filename or "vendas.xlsx", "recebimentos": recebimentos.filename or "recebimentos.xlsx"}
        tempdir = tempfile.mkdtemp(prefix="conciliador_web_")
        tempdir_path = Path(tempdir)
        vendas_path = tempdir_path / filenames["vendas"]
        recebimentos_path = tempdir_path / filenames["recebimentos"]
        output_path = tempdir_path / "conciliacao_objetiva.xlsx"
        started_at = time.perf_counter()

        try:
            await _save_upload(vendas, vendas_path)
            await _save_upload(recebimentos, recebimentos_path)
            if _file_sha256(vendas_path) == _file_sha256(recebimentos_path):
                raise ConciliationUserError("O mesmo arquivo foi enviado em vendas e recebimentos. Selecione um relatório diferente em cada campo.")
            result = await asyncio.wait_for(asyncio.to_thread(run_conciliation, output_path=output_path, vendas_path=vendas_path, recebimentos_path=recebimentos_path), timeout=PROCESSING_TIMEOUT_SECONDS)
        except Exception as exc:
            _cleanup_tempdir(tempdir)
            message = str(exc) if isinstance(exc, ConciliationUserError) else "Falha inesperada ao processar os arquivos."
            _register_execution(db, user_id=user.id, status="Erro", arquivo_vendas=filenames["vendas"], arquivo_recebimentos=filenames["recebimentos"], detalhe=message)
            return _render_conciliation_page(
                request,
                user,
                db,
                error=message,
                submitted_names=filenames,
                selected_client_id=selected_client_id,
                selected_task_id=selected_task_id,
                period_start=period_start,
                period_end=period_end,
            )

        duration_ms = int((time.perf_counter() - started_at) * 1000)
        if not selected_task_id:
            auto_task = create_default_task_for_conciliation(
                db,
                client_id=client.id,
                created_by_user_id=user.id,
                assigned_user_id=client.responsible_user_id,
                competence_date=selected_period_start,
                due_date=selected_period_end,
            )
            selected_task_id = auto_task.id
        token = uuid.uuid4().hex
        download_name = _build_download_name()
        DOWNLOADS[token] = {"tempdir": tempdir, "path": result.arquivo_saida, "download_name": download_name, "created_at": time.time(), "summary": {"arquivo_vendas": filenames["vendas"], "arquivo_recebimentos": filenames["recebimentos"], "qtde_total_processado": result.qtde_linhas_vendas + result.qtde_linhas_recebimentos, "qtde_linhas_vendas": result.qtde_linhas_vendas, "qtde_linhas_recebimentos": result.qtde_linhas_recebimentos, "qtde_recebido_por_dia": result.qtde_recebido_por_dia, "qtde_previsao": result.qtde_previsao, "qtde_vendas_pagas_sem_recebimento": result.qtde_vendas_pagas_sem_recebimento, "arquivo_saida": download_name, "duracao_ms": duration_ms}}
        _register_execution(db, user_id=user.id, status="Concluído", arquivo_vendas=filenames["vendas"], arquivo_recebimentos=filenames["recebimentos"], arquivo_saida=download_name, total_processado=result.qtde_linhas_vendas + result.qtde_linhas_recebimentos, vendas_sem_recebimento=result.qtde_vendas_pagas_sem_recebimento, duracao_ms=duration_ms, detalhe="")
        run = persist_conciliation_run(
            db,
            client_id=client.id,
            task_id=selected_task_id,
            user_id=user.id,
            period_start=selected_period_start,
            period_end=selected_period_end,
            filenames=filenames,
            download_name=download_name,
            result=result,
            duration_ms=duration_ms,
        )
        return _render(
            request,
            user,
            "result.html",
            "operacoes",
            "conciliacao",
            "Conciliação processada",
            "Revise os indicadores do lote e baixe o arquivo consolidado.",
            {
                "download_token": token,
                "summary": DOWNLOADS[token]["summary"],
                "history": load_history(db, limit=5),
                "client_name": client.trade_name or client.legal_name,
                "run_period": f"{selected_period_start.strftime('%d/%m/%Y')} até {selected_period_end.strftime('%d/%m/%Y')}",
                "task_redirect": f"/operacoes/gestor-tarefas/clientes/{client.id}",
                "conciliation_run_id": run.id,
            },
        )


@app.get("/download/{token}")
async def download(request: Request, token: str):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    item = DOWNLOADS.get(token)
    if not item:
        return HTMLResponse("Arquivo indisponível. Gere a conciliação novamente.", status_code=404)
    return FileResponse(path=item["path"], media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=str(item["download_name"]), background=BackgroundTask(lambda: shutil.rmtree(str(item["tempdir"]), ignore_errors=True)))


@app.post("/gestao/financeiro/lancamentos")
@app.post("/fluxo-caixa/lancamentos")
async def create_cashflow_entry(request: Request):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        if not has_permission(user, "edit"):
            _set_flash(request, "Seu perfil não possui permissão para criar lançamentos.", "error")
            return RedirectResponse("/gestao/contas", status_code=status.HTTP_303_SEE_OTHER)
        await _validate_csrf(request)
        form = await request.form()
        try:
            normalized_date = parse_date_input(str(form.get("transaction_date") or "")) or date.today()
            normalized_amount = safe_decimal(str(form.get("amount") or "0"))
            schedule_rows, projection_period = parse_schedule_rows(
                mode=str(form.get("entry_mode") or "avista"),
                transaction_date=normalized_date,
                amount=normalized_amount,
                installment_count=max(int(str(form.get("installment_count") or "2")), 1),
                schedule_dates=[str(item) for item in form.getlist("schedule_date") if str(item).strip()],
                schedule_amounts=[str(item) for item in form.getlist("schedule_amount") if str(item).strip()],
                schedule_labels=[str(item) for item in form.getlist("schedule_label") if str(item).strip()],
                projection_start=parse_date_input(str(form.get("projection_start") or "")),
                projection_end=parse_date_input(str(form.get("projection_end") or "")),
            )
            created_rows = create_internal_finance_entries(
                db,
                user_id=user.id,
                transaction_type=str(form.get("type") or "SAIDA"),
                entry_mode=str(form.get("entry_mode") or "avista"),
                description=_normalize_text_input(str(form.get("description") or "")),
                interested_party=_normalize_text_input(str(form.get("interested_party") or "")),
                category_id=_parse_optional_int(form.get("category_id")),
                subcategory=_normalize_text_input(str(form.get("subcategory") or "")),
                amount=normalized_amount,
                payment_method_id=_parse_optional_int(form.get("payment_method_id")),
                bank_account_id=_parse_optional_int(form.get("bank_account_id")),
                store_id=_parse_optional_int(form.get("store_id")),
                status=str(form.get("status") or "previsto"),
                schedule_rows=schedule_rows,
                projection_period=projection_period,
            )
        except (ConciliationUserError, ValueError) as exc:
            _set_flash(request, str(exc), "error")
            return RedirectResponse("/gestao/financeiro/novo", status_code=status.HTTP_303_SEE_OTHER)

        clear_cashflow_caches()
        if len(created_rows) == 1:
            _set_flash(request, "Lançamento financeiro criado.", "success")
        else:
            _set_flash(request, f"{len(created_rows)} lançamentos financeiros criados.", "success")
        return RedirectResponse("/gestao/contas", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/gestao/financeiro/lancamentos/{transaction_id}/excluir")
@app.post("/fluxo-caixa/lancamentos/{transaction_id}/excluir")
async def delete_cashflow_entry(request: Request, transaction_id: int):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        if not has_permission(user, "edit"):
            _set_flash(request, "Seu perfil não possui permissão para excluir lançamentos.", "error")
            return RedirectResponse("/gestao/contas", status_code=status.HTTP_303_SEE_OTHER)
        await _validate_csrf(request)
        form = await request.form()
        redirect_to = _normalize_redirect_target(str(form.get("redirect_to") or "/gestao/contas"), "/gestao/contas")
        item = db.get(FinancialTransaction, transaction_id)
        if item:
            db.delete(item)
            db.commit()
            clear_cashflow_caches()
            _set_flash(request, "Lançamento removido.", "success")
        else:
            _set_flash(request, "Lançamento não encontrado ou bloqueado.", "error")
        return RedirectResponse(redirect_to, status_code=status.HTTP_303_SEE_OTHER)




@app.post("/cadastros/lojas")
async def create_store(request: Request, name: str = Form(...), code: str = Form(...)):
    return await _simple_create(request, Store(name=name.strip(), code=code.strip().upper()), "/gestao/cadastros", "Loja cadastrada.")


@app.post("/cadastros/contas")
async def create_account(request: Request, name: str = Form(...), bank_name: str = Form(...), branch: str = Form(default=""), account_number: str = Form(default="")):
    return await _simple_create(request, BankAccount(name=name.strip(), bank_name=bank_name.strip(), branch=branch.strip(), account_number=account_number.strip()), "/gestao/cadastros", "Conta salva.")


@app.post("/cadastros/categorias")
async def create_category(request: Request, name: str = Form(...), type: str = Form(...), color: str = Form(default="#22ffc4")):
    return await _simple_create(request, FinancialCategory(name=name.strip(), type=type if type in {"ENTRADA", "SAIDA"} else "ENTRADA", color=color.strip() or "#22ffc4"), "/gestao/cadastros", "Categoria cadastrada.")


@app.post("/cadastros/formas-pagamento")
async def create_payment_method(request: Request, name: str = Form(...), code: str = Form(...)):
    return await _simple_create(request, PaymentMethod(name=name.strip(), code=code.strip().upper()), "/gestao/cadastros", "Forma de pagamento cadastrada.")


async def _simple_create(request: Request, obj, redirect_to: str, success_message: str):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user or not has_permission(user, "manage_settings"):
            return RedirectResponse(redirect_to, status_code=status.HTTP_303_SEE_OTHER)
        await _validate_csrf(request)
        db.add(obj)
        db.commit()
        _set_flash(request, success_message, "success")
        return RedirectResponse(redirect_to, status_code=status.HTTP_303_SEE_OTHER)
