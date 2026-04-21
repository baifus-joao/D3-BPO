from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from conciliador.core.ai_layout import is_ai_layout_enabled

from .bootstrap import cleanup_all_downloads, cleanup_expired_downloads, initialize_database
from .config import settings
from .logging_utils import LOGGER


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    initialize_database()
    cleanup_expired_downloads(getattr(app.state, "downloads", {}), ttl_seconds=settings.download_ttl_seconds)
    LOGGER.info(
        "startup_config ai_layout_enabled=%s openai_layout_model=%s",
        is_ai_layout_enabled(),
        settings.openai_layout_model,
    )
    try:
        yield
    finally:
        cleanup_all_downloads(getattr(app.state, "downloads", {}))
