from __future__ import annotations

import time

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from conciliador.service import ConciliationUserError

from webapp.config import settings
from webapp.dependencies import (
    get_csrf_token,
    get_db_session,
    pop_flash,
    render_page,
    require_user,
    set_flash,
    templates,
    validate_csrf,
)
from webapp.erp import count_active_admins, has_permission, load_history, load_users, normalize_role, serialize_user
from webapp.models import User
from webapp.security import hash_password, verify_password

router = APIRouter()

LOGIN_ATTEMPTS: dict[str, list[float]] = {}
LOGIN_LOCKS: dict[str, float] = {}


def client_identity(request: Request, email: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{host}:{email.strip().lower()}"


@router.get("/")
async def root():
    return RedirectResponse("/hub", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/dashboard")
async def legacy_dashboard():
    return RedirectResponse("/hub", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    with get_db_session() as db:
        user = require_user(request, db)
        if user:
            return RedirectResponse("/hub", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"flash": pop_flash(request), "csrf_token": get_csrf_token(request), "error": None},
    )


@router.post("/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...)):
    try:
        await validate_csrf(request)
    except ConciliationUserError as exc:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"flash": pop_flash(request), "csrf_token": get_csrf_token(request), "error": str(exc)},
        )
    identity = client_identity(request, email)
    now = time.time()
    if LOGIN_LOCKS.get(identity, 0) > now:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "flash": pop_flash(request),
                "csrf_token": get_csrf_token(request),
                "error": "Muitas tentativas de login. Aguarde e tente novamente.",
            },
        )
    with get_db_session() as db:
        user = db.scalar(select(User).where(User.email == email.strip().lower()))
        if not user or not user.is_active or not verify_password(password, user.password_hash):
            attempts = [
                ts for ts in LOGIN_ATTEMPTS.get(identity, [])
                if now - ts <= settings.login_window_seconds
            ] + [now]
            LOGIN_ATTEMPTS[identity] = attempts
            if len(attempts) >= settings.login_max_attempts:
                LOGIN_LOCKS[identity] = now + settings.login_lock_seconds
            return templates.TemplateResponse(
                request,
                "login.html",
                {"flash": pop_flash(request), "csrf_token": get_csrf_token(request), "error": "Credenciais invalidas."},
            )
        request.session["user_id"] = user.id
        request.session["last_seen_at"] = int(now)
        set_flash(request, f"Sessao iniciada como {user.name}.", "success")
        return RedirectResponse("/hub", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
async def logout(request: Request):
    try:
        await validate_csrf(request)
    except ConciliationUserError:
        pass
    request.session.clear()
    set_flash(request, "Sessao encerrada.", "success")
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/hub", response_class=HTMLResponse)
async def hub_page(request: Request):
    with get_db_session() as db:
        user = require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        return templates.TemplateResponse(
            request,
            "hub.html",
            {
                "current_user": serialize_user(user),
                "flash": pop_flash(request),
                "csrf_token": get_csrf_token(request),
            },
        )


@router.get("/gestao")
async def gestao_root():
    return RedirectResponse("/gestao/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/operacoes")
async def operacoes_root():
    return RedirectResponse("/operacoes/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/configuracoes", response_class=HTMLResponse)
async def settings_page(request: Request):
    with get_db_session() as db:
        user = require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        return render_page(
            request,
            user,
            "settings.html",
            "hub",
            "configuracoes",
            "Configuracoes do ambiente",
            "Perfil do usuario, permissoes e administracao compartilhada entre D3 Gestao e D3 Operacoes.",
            {"users": load_users(db) if has_permission(user, "manage_users") else [], "history": load_history(db, limit=20)},
        )


@router.post("/configuracoes/usuario")
async def update_own_profile(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    current_password: str = Form(default=""),
    new_password: str = Form(default=""),
):
    with get_db_session() as db:
        user = require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        await validate_csrf(request)
        duplicate = db.scalar(select(User).where(User.email == email.strip().lower(), User.id != user.id))
        if duplicate:
            set_flash(request, "Ja existe outro usuario com esse e-mail.", "error")
            return RedirectResponse("/configuracoes", status_code=status.HTTP_303_SEE_OTHER)
        user.name = name.strip()
        user.email = email.strip().lower()
        if new_password:
            if len(new_password) < 8 or not verify_password(current_password, user.password_hash):
                set_flash(request, "Senha atual invalida ou nova senha muito curta.", "error")
                return RedirectResponse("/configuracoes", status_code=status.HTTP_303_SEE_OTHER)
            user.password_hash = hash_password(new_password)
        db.commit()
        set_flash(request, "Perfil atualizado.", "success")
        return RedirectResponse("/configuracoes", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/admin/users")
async def create_user(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    role: str = Form(...),
    password: str = Form(...),
):
    with get_db_session() as db:
        user = require_user(request, db)
        if not user or not has_permission(user, "manage_users"):
            return RedirectResponse("/configuracoes", status_code=status.HTTP_303_SEE_OTHER)
        await validate_csrf(request)
        normalized_role = normalize_role(role)
        if len(password) < 8:
            set_flash(request, "A senha precisa ter pelo menos 8 caracteres.", "error")
        elif db.scalar(select(User).where(User.email == email.strip().lower())):
            set_flash(request, "Ja existe um usuario com esse e-mail.", "error")
        else:
            db.add(
                User(
                    name=name.strip(),
                    email=email.strip().lower(),
                    role=normalized_role,
                    password_hash=hash_password(password),
                    is_active=True,
                )
            )
            db.commit()
            set_flash(request, "Usuario criado com sucesso.", "success")
        return RedirectResponse("/configuracoes", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/admin/users/{user_id}/update")
async def update_user(
    request: Request,
    user_id: int,
    name: str = Form(...),
    email: str = Form(...),
    role: str = Form(...),
    is_active: str | None = Form(default=None),
):
    with get_db_session() as db:
        current_user = require_user(request, db)
        if not current_user or not has_permission(current_user, "manage_users"):
            return RedirectResponse("/configuracoes", status_code=status.HTTP_303_SEE_OTHER)
        await validate_csrf(request)
        target = db.get(User, user_id)
        if not target:
            set_flash(request, "Usuario nao encontrado.", "error")
            return RedirectResponse("/configuracoes", status_code=status.HTTP_303_SEE_OTHER)
        new_role = normalize_role(role)
        new_is_active = is_active == "on"
        if target.id == current_user.id:
            new_is_active = True
        if target.role == "admin" and target.is_active and (new_role != "admin" or not new_is_active) and count_active_admins(db) <= 1:
            set_flash(request, "Nao e possivel remover ou desativar o ultimo admin ativo.", "error")
            return RedirectResponse("/configuracoes", status_code=status.HTTP_303_SEE_OTHER)
        target.name = name.strip()
        target.email = email.strip().lower()
        target.role = new_role
        target.is_active = new_is_active
        db.commit()
        set_flash(request, "Usuario atualizado.", "success")
        return RedirectResponse("/configuracoes", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/admin/users/{user_id}/reset-password")
async def reset_password(request: Request, user_id: int, new_password: str = Form(...)):
    with get_db_session() as db:
        current_user = require_user(request, db)
        if not current_user or not has_permission(current_user, "manage_users"):
            return RedirectResponse("/configuracoes", status_code=status.HTTP_303_SEE_OTHER)
        await validate_csrf(request)
        target = db.get(User, user_id)
        if target and len(new_password) >= 8:
            target.password_hash = hash_password(new_password)
            db.commit()
            set_flash(request, "Senha redefinida.", "success")
        else:
            set_flash(request, "Nao foi possivel redefinir a senha.", "error")
        return RedirectResponse("/configuracoes", status_code=status.HTTP_303_SEE_OTHER)
