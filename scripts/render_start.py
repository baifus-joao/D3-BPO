from __future__ import annotations

import os
import subprocess
import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import inspect
from webapp.db import engine


LEGACY_SCHEMA_REVISIONS: tuple[tuple[str, set[str]], ...] = (
    (
        "20260322_0002",
        {
            "d3_users",
            "d3_execution_logs",
            "d3_stores",
            "d3_bank_accounts",
            "d3_financial_categories",
            "d3_payment_methods",
            "d3_financial_transactions",
        },
    ),
    ("20260322_0001", {"d3_users", "d3_execution_logs"}),
)


def _run(*args: str) -> None:
    subprocess.run(args, check=True)


def _detect_legacy_revision(table_names: set[str]) -> str | None:
    for revision, required_tables in LEGACY_SCHEMA_REVISIONS:
        if required_tables.issubset(table_names):
            return revision
    return None


def _prepare_database() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    if "alembic_version" not in table_names:
        revision = _detect_legacy_revision(table_names)
        if revision:
            print(f"[render_start] Legacy schema detected, stamping revision {revision}", flush=True)
            _run(sys.executable, "-m", "alembic", "stamp", revision)

    print("[render_start] Running alembic upgrade head", flush=True)
    _run(sys.executable, "-m", "alembic", "upgrade", "head")


def main() -> None:
    _prepare_database()
    port = os.getenv("PORT", "8000")
    os.execvp(
        sys.executable,
        [
            sys.executable,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            "0.0.0.0",
            "--port",
            port,
        ],
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
