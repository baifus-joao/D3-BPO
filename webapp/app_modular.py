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
    create_task,
    delete_task,
    load_client_detail,
    load_client_open_tasks_for_conciliation,
    load_pending_items,
    load_client_reference_lists,
    load_clients_overview,
    load_operations_queue,
    persist_conciliation_run,
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
    export_cashflow_workbook,
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
        "r?pido": "rápido",
        "Rap?do": "Rápido",
        "R?pido": "Rápido",
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
                "period": f"{run.period_start.strftime('%d/%m/%Y')} ate {run.period_end.strftime('%d/%m/%Y')}",
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
    return f"/operacoes/financeiro/configuracoes{f'?{query}' if query else ''}"


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
            .where(FinancialTransaction.status == "previsto")
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
                    "description": "Fluxo de caixa, cadastros financeiros e relatórios gerenciais vivem aqui, sem se misturar com as ferramentas usadas na entrega aos clientes.",
                    "module_count": 4,
                    "module_label": "Módulos de gestão",
                    "secondary_label": "Lançamentos previstos",
                    "secondary_value": len(upcoming),
                    "history_title": "Histórico de gestão",
                },
            },
        )


@app.get("/operacoes/dashboard", response_class=HTMLResponse)
async def operacoes_dashboard(
    request: Request,
    client_id: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    assigned_user_id: str | None = Query(default=None),
):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        refs = load_client_reference_lists(db)
        queue = load_operations_queue(
            db,
            filters={
                "client_id": _parse_optional_int(client_id),
                "status": (status_value or "").strip(),
                "assigned_user_id": _parse_optional_int(assigned_user_id),
            },
        )
        return _render(
            request,
            user,
            "operations_queue.html",
            "operacoes",
            "dashboard",
            "D3 Operações",
            "Fila operacional da carteira, com tarefas, clientes e últimas conciliações do BPO.",
            {**queue, **refs},
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


@app.get("/operacoes/clientes", response_class=HTMLResponse)
async def clients_page(
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
        return _render(
            request,
            user,
            "clients.html",
            "operacoes",
            "clientes",
            "Carteira de clientes",
            "Base operacional do BPO com responsáveis, contatos e visibilidade da carga de trabalho.",
            {
                **load_clients_overview(
                    db,
                    filters={
                        "status": (status_value or "").strip(),
                        "responsible_user_id": _parse_optional_int(responsible_user_id),
                        "search": search or "",
                    },
                ),
                **refs,
            },
        )


@app.get("/operacoes/financeiro/configuracoes", response_class=HTMLResponse)
async def finance_settings_page(request: Request, client_id: str | None = Query(default=None)):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        refs = load_finance_setup_reference_lists(db)
        selected_client_id = _parse_optional_int(client_id)
        if selected_client_id is None and refs["finance_clients"]:
            active_client = next((item for item in refs["finance_clients"] if item["status"] != "inativo"), None)
            selected_client_id = (active_client or refs["finance_clients"][0])["id"]
        return _render(
            request,
            user,
            "finance_settings.html",
            "operacoes",
            "financeiro",
            "Configuracoes financeiras",
            "Estruture o cadastro financeiro de cada cliente antes de entrar em contas a pagar e receber.",
            {
                **refs,
                **load_finance_setup_overview(db, client_id=selected_client_id),
            },
        )


@app.get("/operacoes/clientes/{client_id}", response_class=HTMLResponse)
async def client_detail_page(request: Request, client_id: int):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        detail = load_client_detail(db, client_id)
        if not detail:
            _set_flash(request, "Cliente não encontrado.", "error")
            return RedirectResponse("/operacoes/clientes", status_code=status.HTTP_303_SEE_OTHER)
        refs = load_client_reference_lists(db)
        return _render(
            request,
            user,
            "client_detail.html",
            "operacoes",
            "clientes",
            detail["client"]["trade_name"],
            "Histórico operacional, tarefas, contatos e conciliações deste cliente.",
            {**detail, **refs},
        )


@app.get("/operacoes/pendencias", response_class=HTMLResponse)
async def pending_items_page(
    request: Request,
    client_id: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    item_type: str | None = Query(default=None),
):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        refs = load_client_reference_lists(db)
        data = load_pending_items(
            db,
            filters={
                "client_id": _parse_optional_int(client_id),
                "status": (status_value or "").strip(),
                "item_type": item_type or "",
            },
        )
        return _render(
            request,
            user,
            "pending_items.html",
            "operacoes",
            "pendencias",
            "Pendências operacionais",
            "Acompanhamento das divergências abertas pela conciliação, com status e contexto por cliente.",
            {**data, **refs},
        )


@app.get("/fluxo-caixa")
async def cashflow_legacy():
    return RedirectResponse("/gestao/fluxo-caixa", status_code=status.HTTP_303_SEE_OTHER)


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
        overview = load_cashflow_overview(db, filters={"date_from": parse_date_input(date_from), "date_to": parse_date_input(date_to), "category_id": normalized_category_id, "store_id": normalized_store_id, "status": status_value, "account_id": normalized_account_id, "type": movement_type}, format_currency=format_currency, format_short_date=format_short_date, page=page)
        form_state = build_cashflow_form_state(db)
        export_query = _build_query_string({"date_from": date_from or "", "date_to": date_to or "", "category_id": normalized_category_id, "store_id": normalized_store_id, "account_id": normalized_account_id, "status": status_value or "", "type": movement_type or ""})
        export_url = f"/gestao/fluxo-caixa/exportar{f'?{export_query}' if export_query else ''}"
        return _render(request, user, "cashflow.html", "gestao", "fluxo_caixa", "Fluxo de caixa da D3", "Controle entradas, saídas, previsões e dados internos preparados para BI.", {**refs, **overview, **form_state, "filters": {"date_from": date_from or "", "date_to": date_to or "", "category_id": normalized_category_id, "store_id": normalized_store_id, "status": status_value or "", "account_id": normalized_account_id, "type": movement_type or ""}, "export_url": export_url})


@app.get("/gestao/fluxo-caixa/exportar")
async def export_cashflow(request: Request, date_from: str | None = Query(default=None), date_to: str | None = Query(default=None), category_id: str | None = Query(default=None), store_id: str | None = Query(default=None), status_value: str | None = Query(default=None, alias="status"), account_id: str | None = Query(default=None), movement_type: str | None = Query(default=None, alias="type")):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        filters = {
            "date_from": parse_date_input(date_from),
            "date_to": parse_date_input(date_to),
            "category_id": _parse_optional_int(category_id),
            "store_id": _parse_optional_int(store_id),
            "status": status_value,
            "account_id": _parse_optional_int(account_id),
            "type": movement_type,
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
            "Relatorios de gestao",
            "Leitura financeira da operacao interna.",
            load_management_reports(db),
        )


@app.get("/operacoes/relatorios", response_class=HTMLResponse)
async def operational_reports_page(request: Request):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        return _render(
            request,
            user,
            "reports.html",
            "operacoes",
            "relatorios",
            "Relatorios operacionais",
            "Leitura das execucoes da equipe.",
            load_operational_reports(db),
        )


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
            "Relatorios",
            "Escolha a area antes de abrir os relatorios.",
            {},
        )




@app.post("/operacoes/clientes")
async def create_bpo_client(
    request: Request,
    legal_name: str = Form(...),
    trade_name: str = Form(default=""),
    document: str = Form(default=""),
    segment: str = Form(default=""),
    responsible_user_id: str | None = Form(default=None),
    notes: str = Form(default=""),
):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user or not has_permission(user, "edit"):
            return RedirectResponse("/operacoes/clientes", status_code=status.HTTP_303_SEE_OTHER)
        await _validate_csrf(request)
        create_client(
            db,
            legal_name=legal_name,
            trade_name=trade_name or legal_name,
            document=document,
            segment=segment,
            responsible_user_id=_parse_optional_int(responsible_user_id),
            notes=notes,
        )
        _set_flash(request, "Cliente da carteira cadastrado.", "success")
        return RedirectResponse("/operacoes/clientes", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/operacoes/clientes/{client_id}/atualizar")
async def update_bpo_client(
    request: Request,
    client_id: int,
    legal_name: str = Form(...),
    trade_name: str = Form(default=""),
    document: str = Form(default=""),
    segment: str = Form(default=""),
    responsible_user_id: str | None = Form(default=None),
    notes: str = Form(default=""),
    status_value: str = Form(default="ativo", alias="status"),
):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user or not has_permission(user, "edit"):
            return RedirectResponse(f"/operacoes/clientes/{client_id}", status_code=status.HTTP_303_SEE_OTHER)
        await _validate_csrf(request)
        client = update_client(
            db,
            client_id=client_id,
            legal_name=legal_name,
            trade_name=trade_name,
            document=document,
            segment=segment,
            responsible_user_id=_parse_optional_int(responsible_user_id),
            notes=notes,
            status=status_value,
        )
        if not client:
            _set_flash(request, "Cliente não encontrado.", "error")
            return RedirectResponse("/operacoes/clientes", status_code=status.HTTP_303_SEE_OTHER)
        _set_flash(request, "Cliente atualizado.", "success")
        return RedirectResponse(f"/operacoes/clientes/{client_id}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/operacoes/clientes/{client_id}/arquivar")
async def archive_bpo_client(request: Request, client_id: int):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user or not has_permission(user, "edit"):
            return RedirectResponse(f"/operacoes/clientes/{client_id}", status_code=status.HTTP_303_SEE_OTHER)
        await _validate_csrf(request)
        client = archive_client(db, client_id=client_id)
        if not client:
            _set_flash(request, "Cliente não encontrado.", "error")
            return RedirectResponse("/operacoes/clientes", status_code=status.HTTP_303_SEE_OTHER)
        _set_flash(request, "Cliente arquivado na carteira.", "success")
        return RedirectResponse("/operacoes/clientes", status_code=status.HTTP_303_SEE_OTHER)


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
            return RedirectResponse(f"/operacoes/clientes/{client_id}", status_code=status.HTTP_303_SEE_OTHER)
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
        return RedirectResponse(f"/operacoes/clientes/{client_id}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/operacoes/clientes/{client_id}/tarefas")
async def create_bpo_task(
    request: Request,
    client_id: int,
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
            return RedirectResponse(f"/operacoes/clientes/{client_id}", status_code=status.HTTP_303_SEE_OTHER)
        await _validate_csrf(request)
        create_task(
            db,
            client_id=client_id,
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
        return RedirectResponse(f"/operacoes/clientes/{client_id}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/operacoes/tarefas/{task_id}/atualizar")
async def update_bpo_task(
    request: Request,
    task_id: int,
    redirect_to: str = Form(default="/operacoes/dashboard"),
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
                "run_period": f"{selected_period_start.strftime('%d/%m/%Y')} ate {selected_period_end.strftime('%d/%m/%Y')}",
                "task_redirect": f"/operacoes/clientes/{client.id}",
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


@app.post("/fluxo-caixa/lancamentos")
async def create_cashflow_entry(request: Request, transaction_date: str = Form(...), type: str = Form(...), description: str = Form(default=""), category_id: str | None = Form(default=None), subcategory: str = Form(default=""), amount: str = Form(...), payment_method_id: str | None = Form(default=None), bank_account_id: str | None = Form(default=None), store_id: str | None = Form(default=None), status_value: str = Form(..., alias="status"), planned_date: str | None = Form(default=None), realized_date: str | None = Form(default=None)):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        if not has_permission(user, "edit"):
            _set_flash(request, "Seu perfil não possui permissão para criar lançamentos.", "error")
            return RedirectResponse("/gestao/fluxo-caixa", status_code=status.HTTP_303_SEE_OTHER)
        await _validate_csrf(request)
        normalized_date = parse_date_input(transaction_date) or date.today()
        normalized_status = status_value if status_value in {"previsto", "realizado"} else "previsto"
        normalized_type = type if type in {"ENTRADA", "SAIDA"} else "ENTRADA"
        normalized_description = _normalize_text_input(description)
        if not normalized_description:
            normalized_description = _normalize_text_input(subcategory) or "Lançamento manual"
        normalized_subcategory = _normalize_text_input(subcategory)

        normalized_planned = parse_date_input(planned_date) or normalized_date
        normalized_realized = parse_date_input(realized_date) or (normalized_date if normalized_status == "realizado" else None)
        if normalized_status == "previsto":
            normalized_realized = None

        db.add(FinancialTransaction(transaction_date=normalized_date, type=normalized_type, description=normalized_description, category_id=_parse_optional_int(category_id), subcategory=normalized_subcategory, amount=safe_decimal(amount), payment_method_id=_parse_optional_int(payment_method_id), bank_account_id=_parse_optional_int(bank_account_id), store_id=_parse_optional_int(store_id), source="manual", status=normalized_status, planned_date=normalized_planned, realized_date=normalized_realized, created_by_user_id=user.id))
        db.commit()
        _set_flash(request, "Lançamento financeiro criado.", "success")
        return RedirectResponse("/gestao/fluxo-caixa", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/fluxo-caixa/lancamentos/{transaction_id}/excluir")
async def delete_cashflow_entry(request: Request, transaction_id: int):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        if not has_permission(user, "edit"):
            _set_flash(request, "Seu perfil não possui permissão para excluir lançamentos.", "error")
            return RedirectResponse("/gestao/fluxo-caixa", status_code=status.HTTP_303_SEE_OTHER)
        await _validate_csrf(request)
        item = db.get(FinancialTransaction, transaction_id)
        if item and item.source != "conciliacao":
            db.delete(item)
            db.commit()
            _set_flash(request, "Lançamento removido.", "success")
        else:
            _set_flash(request, "Lançamento não encontrado ou bloqueado.", "error")
        return RedirectResponse("/gestao/fluxo-caixa", status_code=status.HTTP_303_SEE_OTHER)




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
