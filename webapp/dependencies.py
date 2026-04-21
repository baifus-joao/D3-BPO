from __future__ import annotations

import time
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from conciliador.service import ConciliationUserError

from .config import settings
from .db import SessionLocal
from .erp import CONTEXTS, ROLE_LABELS, build_contexts, build_nav, permission_flags, serialize_user
from .logging_utils import LOGGER
from .models import User

BASE_DIR = Path(__file__).resolve().parent


def format_currency(value) -> str:
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    text = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {text}"


def format_short_date(value) -> str:
    if not value:
        return "-"
    if isinstance(value, datetime):
        value = value.date()
    return value.strftime("%d/%m/%Y")


templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.filters["currency"] = format_currency
templates.env.filters["shortdate"] = format_short_date


def get_db_session() -> Session:
    return SessionLocal()


def set_flash(request: Request, message: str, level: str = "info") -> None:
    request.session["flash"] = {"message": message, "level": level}


def pop_flash(request: Request):
    return request.session.pop("flash", None)


def get_csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = uuid.uuid4().hex
        request.session["csrf_token"] = token
    return token


async def validate_csrf(request: Request) -> None:
    form = await request.form()
    if str(form.get("csrf_token", "")) != str(request.session.get("csrf_token", "")):
        raise ConciliationUserError("Sessao invalida ou expirada. Atualize a pagina e tente novamente.")


def validate_csrf_header(request: Request) -> None:
    token = request.headers.get("X-CSRF-Token", "")
    if str(token) != str(request.session.get("csrf_token", "")):
        raise ConciliationUserError("Sessao invalida ou expirada. Atualize a pagina e tente novamente.")


def require_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    now = int(time.time())
    if now - int(request.session.get("last_seen_at", now)) > settings.session_max_age_seconds:
        request.session.clear()
        return None
    request.session["last_seen_at"] = now
    user = db.get(User, user_id)
    if not user or not user.is_active:
        request.session.clear()
        return None
    return user


def build_base_context(
    request: Request,
    user: User,
    area: str,
    active_module: str,
    title: str,
    subtitle: str,
) -> dict[str, object]:
    return {
        "current_user": serialize_user(user),
        "nav_items": build_nav(area, active_module),
        "context_items": build_contexts(area),
        "current_area": area,
        "current_area_meta": CONTEXTS.get(area, CONTEXTS["hub"]),
        "page_title": title,
        "page_subtitle": subtitle,
        "flash": pop_flash(request),
        "csrf_token": get_csrf_token(request),
        "permissions": permission_flags(user),
        "role_labels": ROLE_LABELS,
    }


def render_page(
    request: Request,
    user: User,
    template_name: str,
    area: str,
    active_module: str,
    title: str,
    subtitle: str,
    extra: dict[str, object] | None = None,
):
    context = build_base_context(request, user, area, active_module, title, subtitle)
    if extra:
        context.update(extra)
    return templates.TemplateResponse(request, template_name, context)
