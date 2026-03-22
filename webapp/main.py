from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
import tempfile
import time
import uuid
from datetime import datetime
from os import getenv
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask
from starlette.middleware.sessions import SessionMiddleware

from conciliador.core.ai_layout import is_ai_layout_enabled
from conciliador.service import ConciliationUserError, run_conciliation

from .db import Base, DATABASE_URL, SessionLocal, engine
from .models import ExecutionLog, User
from .security import hash_password, verify_password


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
DOWNLOADS: dict[str, dict[str, object]] = {}


def _load_local_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_local_env()

MAX_UPLOAD_SIZE = 15 * 1024 * 1024
PROCESSING_TIMEOUT_SECONDS = 60
LOGGER = logging.getLogger("conciliador.web")
SESSION_MAX_AGE_SECONDS = int(getenv("SESSION_MAX_AGE_SECONDS", str(60 * 60 * 8)))
LOGIN_MAX_ATTEMPTS = int(getenv("LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_WINDOW_SECONDS = int(getenv("LOGIN_WINDOW_SECONDS", str(15 * 60)))
LOGIN_LOCK_SECONDS = int(getenv("LOGIN_LOCK_SECONDS", str(10 * 60)))
DOWNLOAD_TTL_SECONDS = int(getenv("DOWNLOAD_TTL_SECONDS", str(60 * 60)))
LOGIN_ATTEMPTS: dict[str, list[float]] = {}
LOGIN_LOCKS: dict[str, float] = {}

SESSION_SECRET = getenv("SESSION_SECRET", "dev-session-secret-change-me")
SESSION_DOMAIN = getenv("SESSION_DOMAIN")
SESSION_HTTPS_ONLY = getenv("SESSION_HTTPS_ONLY", "false").lower() == "true"
SESSION_SAME_SITE = getenv("SESSION_SAME_SITE", "lax")

app = FastAPI(title="Painel D3")
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site=SESSION_SAME_SITE,
    https_only=SESSION_HTTPS_ONLY,
    domain=SESSION_DOMAIN,
    max_age=SESSION_MAX_AGE_SECONDS,
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

if not LOGGER.handlers:
    LOGGER.setLevel(logging.INFO)
    handler = logging.FileHandler(PROJECT_ROOT / "conciliador_web.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.addHandler(handler)


def _cleanup_tempdir(tempdir: str) -> None:
    shutil.rmtree(tempdir, ignore_errors=True)


def _cleanup_expired_downloads(now: float | None = None) -> None:
    reference = now or time.time()
    expired_tokens = [
        token
        for token, item in DOWNLOADS.items()
        if reference - float(item.get("created_at", reference)) > DOWNLOAD_TTL_SECONDS
    ]
    for token in expired_tokens:
        item = DOWNLOADS.pop(token, None)
        if item:
            _cleanup_tempdir(str(item["tempdir"]))


def _set_flash(request: Request, message: str, level: str = "info") -> None:
    request.session["flash"] = {"message": message, "level": level}


def _pop_flash(request: Request) -> dict[str, str] | None:
    return request.session.pop("flash", None)


def _get_csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = uuid.uuid4().hex
        request.session["csrf_token"] = token
    return token


async def _validate_csrf(request: Request) -> None:
    form = await request.form()
    submitted = str(form.get("csrf_token", ""))
    expected = str(request.session.get("csrf_token", ""))
    if not submitted or not expected or submitted != expected:
        raise ConciliationUserError("Sessao invalida ou expirada. Atualize a pagina e tente novamente.")


def _client_identity(request: Request, email: str | None = None) -> str:
    host = request.client.host if request.client else "unknown"
    normalized_email = email.strip().lower() if email else ""
    return f"{host}:{normalized_email}"


def _prune_login_state(now: float) -> None:
    for key, attempts in list(LOGIN_ATTEMPTS.items()):
        recent = [ts for ts in attempts if now - ts <= LOGIN_WINDOW_SECONDS]
        if recent:
            LOGIN_ATTEMPTS[key] = recent
        else:
            LOGIN_ATTEMPTS.pop(key, None)

    for key, locked_until in list(LOGIN_LOCKS.items()):
        if locked_until <= now:
            LOGIN_LOCKS.pop(key, None)


def _login_lock_message(seconds_remaining: int) -> str:
    minutes = max(1, round(seconds_remaining / 60))
    return f"Muitas tentativas de login. Aguarde cerca de {minutes} minuto(s) e tente novamente."


def _count_active_admins(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True))
        )
        or 0
    )


def _history_status_class(status_value: str) -> str:
    normalized = status_value.strip().lower()
    if normalized == "concluído" or normalized == "concluido":
        return "success"
    if normalized == "timeout":
        return "warning"
    if normalized == "erro":
        return "error"
    return "neutral"


def _bootstrap_admin(db: Session) -> None:
    admin_exists = db.scalar(select(func.count()).select_from(User).where(User.role == "admin"))
    if admin_exists:
        return

    email = getenv("D3_BOOTSTRAP_ADMIN_EMAIL", "admin@d3financeiro.local").strip().lower()
    password = getenv("D3_BOOTSTRAP_ADMIN_PASSWORD", "Admin123!").strip()
    name = getenv("D3_BOOTSTRAP_ADMIN_NAME", "Administrador D3").strip()

    if getenv("RENDER") and (email == "admin@d3financeiro.local" or password == "Admin123!"):
        raise RuntimeError("Defina credenciais bootstrap do admin antes do deploy em producao.")

    db.add(
        User(
            name=name,
            email=email,
            role="admin",
            password_hash=hash_password(password),
            is_active=True,
        )
    )
    db.commit()
    LOGGER.warning("bootstrap_admin_created email=%s", email)


def _init_db() -> None:
    if getenv("RENDER") and SESSION_SECRET == "dev-session-secret-change-me":
        raise RuntimeError("Defina SESSION_SECRET antes do deploy em producao.")

    if DATABASE_URL.startswith("sqlite"):
        Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        _bootstrap_admin(db)


@app.on_event("startup")
def on_startup() -> None:
    _init_db()
    _cleanup_expired_downloads()
    LOGGER.info(
        "startup_config ai_layout_enabled=%s openai_layout_model=%s session_domain=%s",
        is_ai_layout_enabled(),
        getenv("OPENAI_LAYOUT_MODEL", ""),
        SESSION_DOMAIN or "",
    )


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "script-src 'self' 'unsafe-inline'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    return response


def _get_db() -> Session:
    return SessionLocal()


def _build_download_name() -> str:
    return f"conciliacao_{datetime.now().strftime('%Y-%m-%d_%H%M')}.xlsx"


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
                raise ConciliationUserError(
                    f"O arquivo '{upload.filename or target.name}' excede o limite de 15 MB."
                )
            buffer.write(chunk)
    await upload.close()
    return total_size


def _serialize_user(user: User) -> dict[str, object]:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
    }


def _require_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None

    now = int(time.time())
    last_seen_at = int(request.session.get("last_seen_at", now))
    if now - last_seen_at > SESSION_MAX_AGE_SECONDS:
        request.session.clear()
        return None
    request.session["last_seen_at"] = now

    user = db.get(User, user_id)
    if not user or not user.is_active:
        request.session.clear()
        return None
    return user


def _is_admin(user: User) -> bool:
    return user.role == "admin"


def _load_history(db: Session, limit: int = 20) -> list[dict[str, object]]:
    rows = db.scalars(select(ExecutionLog).order_by(desc(ExecutionLog.created_at)).limit(limit)).all()
    return [
        {
            "executed_at": row.created_at.strftime("%d/%m/%Y %H:%M"),
            "user_name": row.user.name if row.user else "Usuário removido",
            "user_role": row.user.role if row.user else "-",
            "arquivo_vendas": row.arquivo_vendas,
            "arquivo_recebimentos": row.arquivo_recebimentos,
            "arquivo_saida": row.arquivo_saida,
            "qtde_total_processado": row.total_processado,
            "qtde_vendas_pagas_sem_recebimento": row.vendas_sem_recebimento,
            "duracao_ms": row.duracao_ms,
            "status": row.status,
            "status_class": _history_status_class(row.status),
            "detalhe": row.detalhe,
        }
        for row in rows
    ]


def _load_users(db: Session) -> list[dict[str, object]]:
    users = db.scalars(select(User).order_by(User.role.desc(), User.name.asc())).all()
    return [_serialize_user(user) for user in users]


def _render_login(request: Request, error: str | None = None) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "error": error,
            "flash": _pop_flash(request),
            "csrf_token": _get_csrf_token(request),
        },
    )


def _render_dashboard(
    request: Request,
    db: Session,
    user: User,
    error: str | None = None,
    submitted_names: dict[str, str] | None = None,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "error": error,
            "submitted_names": submitted_names or {},
            "current_user": _serialize_user(user),
            "history": _load_history(db),
            "users": _load_users(db) if _is_admin(user) else [],
            "flash": _pop_flash(request),
            "is_admin": _is_admin(user),
            "csrf_token": _get_csrf_token(request),
        },
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    with _get_db() as db:
        user = _require_user(request, db)
        if user:
            return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    return _render_login(request)


@app.get("/healthz")
async def healthz():
    try:
        with _get_db() as db:
            db.execute(select(1))
        return {"status": "ok"}
    except Exception as exc:
        LOGGER.exception("healthcheck_failed")
        return HTMLResponse(f"database_unavailable: {exc}", status_code=503)


@app.post("/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...)):
    try:
        await _validate_csrf(request)
    except ConciliationUserError as exc:
        return _render_login(request, str(exc))
    normalized_email = email.strip().lower()
    identity = _client_identity(request, normalized_email)
    now = time.time()
    _prune_login_state(now)

    locked_until = LOGIN_LOCKS.get(identity)
    if locked_until and locked_until > now:
        return _render_login(request, _login_lock_message(int(locked_until - now)))

    with _get_db() as db:
        user = db.scalar(select(User).where(User.email == normalized_email))
        if not user or not user.is_active or not verify_password(password, user.password_hash):
            attempts = LOGIN_ATTEMPTS.get(identity, [])
            attempts.append(now)
            LOGIN_ATTEMPTS[identity] = [ts for ts in attempts if now - ts <= LOGIN_WINDOW_SECONDS]
            if len(LOGIN_ATTEMPTS[identity]) >= LOGIN_MAX_ATTEMPTS:
                LOGIN_LOCKS[identity] = now + LOGIN_LOCK_SECONDS
                LOGIN_ATTEMPTS.pop(identity, None)
                return _render_login(request, _login_lock_message(LOGIN_LOCK_SECONDS))
            return _render_login(request, "Credenciais inválidas.")

        LOGIN_ATTEMPTS.pop(identity, None)
        LOGIN_LOCKS.pop(identity, None)
        request.session["user_id"] = user.id
        request.session["last_seen_at"] = int(now)
        _set_flash(request, f"Sessão iniciada como {user.name}.", "success")
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/logout")
async def logout(request: Request):
    try:
        await _validate_csrf(request)
    except ConciliationUserError:
        request.session.clear()
        _set_flash(request, "Sessao expirada. Entre novamente.", "error")
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    request.session.clear()
    _set_flash(request, "Sessão encerrada.", "success")
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        return _render_dashboard(request, db, user)


def _register_execution(
    db: Session,
    *,
    user_id: int,
    status_value: str,
    arquivo_vendas: str,
    arquivo_recebimentos: str,
    arquivo_saida: str = "",
    total_processado: int = 0,
    vendas_sem_recebimento: int = 0,
    duracao_ms: int = 0,
    detalhe: str = "",
) -> None:
    db.add(
        ExecutionLog(
            user_id=user_id,
            status=status_value,
            arquivo_vendas=arquivo_vendas,
            arquivo_recebimentos=arquivo_recebimentos,
            arquivo_saida=arquivo_saida,
            total_processado=total_processado,
            vendas_sem_recebimento=vendas_sem_recebimento,
            duracao_ms=duracao_ms,
            detalhe=detalhe,
        )
    )
    db.commit()


@app.post("/conciliar")
async def conciliar(
    request: Request,
    vendas: UploadFile = File(...),
    recebimentos: UploadFile = File(...),
):
    _cleanup_expired_downloads()
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        try:
            await _validate_csrf(request)
        except ConciliationUserError as exc:
            return _render_dashboard(request, db, user, str(exc))

        filenames = {
            "vendas": vendas.filename or "vendas.xlsx",
            "recebimentos": recebimentos.filename or "recebimentos.xlsx",
        }

        for label, filename in filenames.items():
            suffix = Path(filename).suffix.lower()
            if suffix not in {".xlsx", ".xls"}:
                return _render_dashboard(
                    request,
                    db,
                    user,
                    f"O arquivo de {label} precisa ser uma planilha Excel (.xlsx ou .xls).",
                    filenames,
                )

        tempdir = tempfile.mkdtemp(prefix="conciliador_web_")
        tempdir_path = Path(tempdir)
        vendas_path = tempdir_path / filenames["vendas"]
        recebimentos_path = tempdir_path / filenames["recebimentos"]
        output_path = tempdir_path / "conciliacao_objetiva.xlsx"
        started_at = time.perf_counter()

        try:
            vendas_size = await _save_upload(vendas, vendas_path)
            recebimentos_size = await _save_upload(recebimentos, recebimentos_path)
            if _file_sha256(vendas_path) == _file_sha256(recebimentos_path):
                raise ConciliationUserError(
                    "O mesmo arquivo foi enviado em vendas e recebimentos. Selecione um relatório diferente em cada campo."
                )

            result = await asyncio.wait_for(
                asyncio.to_thread(
                    run_conciliation,
                    output_path=output_path,
                    vendas_path=vendas_path,
                    recebimentos_path=recebimentos_path,
                ),
                timeout=PROCESSING_TIMEOUT_SECONDS,
            )
        except ConciliationUserError as exc:
            _cleanup_tempdir(tempdir)
            _register_execution(
                db,
                user_id=user.id,
                status_value="Erro",
                arquivo_vendas=filenames["vendas"],
                arquivo_recebimentos=filenames["recebimentos"],
                detalhe=str(exc),
            )
            LOGGER.warning(
                "status=error tipo=user_error user=%s vendas=%s recebimentos=%s detalhe=%s",
                user.email,
                filenames["vendas"],
                filenames["recebimentos"],
                str(exc),
            )
            return _render_dashboard(request, db, user, str(exc), filenames)
        except TimeoutError:
            _cleanup_tempdir(tempdir)
            message = "O processamento excedeu o tempo limite. Tente novamente com relatórios menores ou revise os arquivos enviados."
            _register_execution(
                db,
                user_id=user.id,
                status_value="Timeout",
                arquivo_vendas=filenames["vendas"],
                arquivo_recebimentos=filenames["recebimentos"],
                detalhe=message,
            )
            LOGGER.warning(
                "status=error tipo=timeout user=%s vendas=%s recebimentos=%s timeout=%ss",
                user.email,
                filenames["vendas"],
                filenames["recebimentos"],
                PROCESSING_TIMEOUT_SECONDS,
            )
            return _render_dashboard(request, db, user, message, filenames)
        except Exception:
            _cleanup_tempdir(tempdir)
            message = "Falha inesperada ao processar os arquivos. Revise os relatórios e tente novamente."
            _register_execution(
                db,
                user_id=user.id,
                status_value="Erro",
                arquivo_vendas=filenames["vendas"],
                arquivo_recebimentos=filenames["recebimentos"],
                detalhe=message,
            )
            LOGGER.exception(
                "status=error tipo=unexpected user=%s vendas=%s recebimentos=%s",
                user.email,
                filenames["vendas"],
                filenames["recebimentos"],
            )
            return _render_dashboard(request, db, user, message, filenames)

        token = uuid.uuid4().hex
        download_name = _build_download_name()
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        total_processado = result.qtde_linhas_vendas + result.qtde_linhas_recebimentos

        DOWNLOADS[token] = {
            "tempdir": tempdir,
            "path": result.arquivo_saida,
            "download_name": download_name,
            "created_at": time.time(),
            "summary": {
                "arquivo_vendas": filenames["vendas"],
                "arquivo_recebimentos": filenames["recebimentos"],
                "qtde_linhas_vendas": result.qtde_linhas_vendas,
                "qtde_linhas_recebimentos": result.qtde_linhas_recebimentos,
                "qtde_total_processado": total_processado,
                "qtde_recebido_por_dia": result.qtde_recebido_por_dia,
                "qtde_previsao": result.qtde_previsao,
                "qtde_vendas_pagas_sem_recebimento": result.qtde_vendas_pagas_sem_recebimento,
                "arquivo_saida": download_name,
                "duracao_ms": duration_ms,
            },
        }

        _register_execution(
            db,
            user_id=user.id,
            status_value="Concluído",
            arquivo_vendas=filenames["vendas"],
            arquivo_recebimentos=filenames["recebimentos"],
            arquivo_saida=download_name,
            total_processado=total_processado,
            vendas_sem_recebimento=result.qtde_vendas_pagas_sem_recebimento,
            duracao_ms=duration_ms,
        )
        LOGGER.info(
            "status=success user=%s vendas=%s recebimentos=%s vendas_bytes=%s recebimentos_bytes=%s linhas_vendas=%s linhas_recebimentos=%s duracao_ms=%s",
            user.email,
            filenames["vendas"],
            filenames["recebimentos"],
            vendas_size,
            recebimentos_size,
            result.qtde_linhas_vendas,
            result.qtde_linhas_recebimentos,
            duration_ms,
        )
        return templates.TemplateResponse(
            request,
            "result.html",
            {
                "download_token": token,
                "summary": DOWNLOADS[token]["summary"],
                "current_user": _serialize_user(user),
                "history": _load_history(db, limit=5),
                "csrf_token": _get_csrf_token(request),
            },
        )


@app.post("/admin/users")
async def create_user(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    role: str = Form(...),
    password: str = Form(...),
):
    with _get_db() as db:
        user = _require_user(request, db)
        if not user or not _is_admin(user):
            return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
        try:
            await _validate_csrf(request)
        except ConciliationUserError as exc:
            _set_flash(request, str(exc), "error")
            return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)

        normalized_email = email.strip().lower()
        if role not in {"admin", "colaborador"}:
            _set_flash(request, "Perfil inválido.", "error")
            return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
        if len(password) < 8:
            _set_flash(request, "A senha precisa ter pelo menos 8 caracteres.", "error")
            return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
        if db.scalar(select(User).where(User.email == normalized_email)):
            _set_flash(request, "Já existe um usuário com esse e-mail.", "error")
            return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)

        db.add(
            User(
                name=name.strip(),
                email=normalized_email,
                role=role,
                password_hash=hash_password(password),
                is_active=True,
            )
        )
        db.commit()
        _set_flash(request, "Usuário criado com sucesso.", "success")
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/users/{user_id}/update")
async def update_user(
    request: Request,
    user_id: int,
    name: str = Form(...),
    email: str = Form(...),
    role: str = Form(...),
    is_active: str | None = Form(default=None),
):
    with _get_db() as db:
        current_user = _require_user(request, db)
        if not current_user or not _is_admin(current_user):
            return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
        try:
            await _validate_csrf(request)
        except ConciliationUserError as exc:
            _set_flash(request, str(exc), "error")
            return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)

        target = db.get(User, user_id)
        if not target:
            _set_flash(request, "Usuário não encontrado.", "error")
            return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)

        normalized_email = email.strip().lower()
        duplicate = db.scalar(select(User).where(User.email == normalized_email, User.id != user_id))
        if duplicate:
            _set_flash(request, "Já existe outro usuário com esse e-mail.", "error")
            return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)

        target.name = name.strip()
        target.email = normalized_email
        new_role = role if role in {"admin", "colaborador"} else target.role
        new_is_active = is_active == "on"
        if target.id == current_user.id:
            new_is_active = True

        if target.role == "admin" and target.is_active and (new_role != "admin" or not new_is_active):
            if _count_active_admins(db) <= 1:
                _set_flash(request, "Nao e possivel remover ou desativar o ultimo admin ativo.", "error")
                return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)

        target.role = new_role
        target.is_active = new_is_active

        db.commit()
        _set_flash(request, "Usuário atualizado.", "success")
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/users/{user_id}/reset-password")
async def reset_password(
    request: Request,
    user_id: int,
    new_password: str = Form(...),
):
    with _get_db() as db:
        current_user = _require_user(request, db)
        if not current_user or not _is_admin(current_user):
            return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
        try:
            await _validate_csrf(request)
        except ConciliationUserError as exc:
            _set_flash(request, str(exc), "error")
            return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)

        target = db.get(User, user_id)
        if not target:
            _set_flash(request, "Usuário não encontrado.", "error")
            return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
        if len(new_password) < 8:
            _set_flash(request, "A nova senha precisa ter pelo menos 8 caracteres.", "error")
            return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)

        target.password_hash = hash_password(new_password)
        db.commit()
        _set_flash(request, f"Senha redefinida para {target.name}.", "success")
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


def _cleanup_download(token: str) -> None:
    item = DOWNLOADS.pop(token, None)
    if item:
        _cleanup_tempdir(str(item["tempdir"]))


@app.get("/download/{token}")
async def download(request: Request, token: str):
    _cleanup_expired_downloads()
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        request.session["last_seen_at"] = int(time.time())

    item = DOWNLOADS.get(token)
    if not item:
        return HTMLResponse("Arquivo indisponível. Gere a conciliação novamente.", status_code=404)

    return FileResponse(
        path=item["path"],
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=str(item["download_name"]),
        background=BackgroundTask(_cleanup_download, token),
    )
