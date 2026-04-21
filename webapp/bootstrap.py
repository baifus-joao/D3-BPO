from __future__ import annotations

import shutil
import time
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from .bpo_services import seed_bpo_data
from .config import settings
from .db import SessionLocal
from .erp import seed_cashflow_data, seed_reference_data
from .models import User
from .security import hash_password


def initialize_database() -> None:
    try:
        with SessionLocal() as db:
            if not db.scalar(select(func.count()).select_from(User).where(User.role == "admin")):
                db.add(
                    User(
                        name=settings.bootstrap_admin_name,
                        email=settings.bootstrap_admin_email,
                        role="admin",
                        password_hash=hash_password(settings.bootstrap_admin_password),
                        is_active=True,
                    )
                )
                db.commit()
            seed_reference_data(db)
            seed_cashflow_data(db)
            seed_bpo_data(db)
    except SQLAlchemyError as exc:
        raise RuntimeError(
            "Banco de dados indisponivel ou schema nao inicializado. "
            "Execute 'alembic upgrade head' antes de iniciar a aplicacao."
        ) from exc


def cleanup_expired_downloads(
    downloads: dict[str, dict[str, Any]],
    ttl_seconds: int | None = None,
) -> None:
    effective_ttl = settings.download_ttl_seconds if ttl_seconds is None else ttl_seconds
    now = time.time()
    for token, item in list(downloads.items()):
        created_at = float(item.get("created_at", now))
        if now - created_at > effective_ttl:
            tempdir = item.get("tempdir")
            if tempdir:
                shutil.rmtree(str(tempdir), ignore_errors=True)
            downloads.pop(token, None)


def cleanup_all_downloads(downloads: dict[str, dict[str, Any]]) -> None:
    for item in downloads.values():
        tempdir = item.get("tempdir")
        if tempdir:
            shutil.rmtree(str(tempdir), ignore_errors=True)
    downloads.clear()
