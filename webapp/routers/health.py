from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from webapp.dependencies import LOGGER, get_db_session

router = APIRouter()


@router.get("/healthz")
async def healthz():
    return {"status": "ok"}


@router.get("/readyz")
async def readyz():
    try:
        with get_db_session() as db:
            db.execute(select(1))
        return {"status": "ok", "database": "ok"}
    except Exception as exc:
        LOGGER.exception("readiness_check_failed")
        return HTMLResponse(f"database_unavailable: {exc}", status_code=503)
