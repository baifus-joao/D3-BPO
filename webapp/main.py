from __future__ import annotations

import asyncio
import hashlib
import logging
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

from conciliador.service import ConciliationUserError, run_conciliation

from .db import Base, SessionLocal, engine
from .models import ExecutionLog, User
from .security import hash_password, verify_password


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
DOWNLOADS: dict[str, dict[str, object]] = {}
MAX_UPLOAD_SIZE = 15 * 1024 * 1024
PROCESSING_TIMEOUT_SECONDS = 60
LOGGER = logging.getLogger("conciliador.web")
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
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

if not LOGGER.handlers:
    LOGGER.setLevel(logging.INFO)
    handler = logging.FileHandler(BASE_DIR.parent / "conciliador_web.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.addHandler(handler)


def _cleanup_tempdir(tempdir: str) -> None:
    shutil.rmtree(tempdir, ignore_errors=True)


def _set_flash(request: Request, message: str, level: str = "info") -> None:
    request.session["flash"] = {"message": message, "level": level}


def _pop_flash(request: Request) -> dict[str, str] | None:
    return request.session.pop("flash", None)


def _bootstrap_admin(db: Session) -> None:
    admin_exists = db.scalar(select(func.count()).select_from(User).where(User.role == "admin"))
    if admin_exists:
        return

    email = getenv("D3_BOOTSTRAP_ADMIN_EMAIL", "admin@d3financeiro.local").strip().lower()
    password = getenv("D3_BOOTSTRAP_ADMIN_PASSWORD", "Admin123!").strip()
    name = getenv("D3_BOOTSTRAP_ADMIN_NAME", "Administrador D3").strip()

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

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        _bootstrap_admin(db)


@app.on_event("startup")
def on_startup() -> None:
    _init_db()


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
    with _get_db() as db:
        user = db.scalar(select(User).where(User.email == email.strip().lower()))
        if not user or not user.is_active or not verify_password(password, user.password_hash):
            return _render_login(request, "Credenciais inválidas.")

        request.session["user_id"] = user.id
        _set_flash(request, f"Sessão iniciada como {user.name}.", "success")
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/logout")
async def logout(request: Request):
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
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

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
        target.role = role if role in {"admin", "colaborador"} else target.role
        target.is_active = is_active == "on"
        if target.id == current_user.id:
            target.is_active = True

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
    with _get_db() as db:
        user = _require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    item = DOWNLOADS.get(token)
    if not item:
        return HTMLResponse("Arquivo indisponível. Gere a conciliação novamente.", status_code=404)

    return FileResponse(
        path=item["path"],
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=str(item["download_name"]),
        background=BackgroundTask(_cleanup_download, token),
    )
