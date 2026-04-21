from __future__ import annotations

import os
import subprocess
import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import inspect, text
from webapp.db import engine


SCHEMA_REVISIONS: tuple[tuple[str, set[str]], ...] = (
    ("20260322_0001", {"d3_users", "d3_execution_logs"}),
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
    (
        "20260326_0003",
        {
            "bpo_clients",
            "bpo_task_templates",
            "bpo_client_contacts",
            "bpo_recurring_routines",
            "bpo_tasks",
            "bpo_task_events",
            "bpo_conciliation_runs",
            "bpo_conciliation_items",
        },
    ),
    (
        "20260326_0004",
        {
            "bpo_fin_bank_accounts",
            "bpo_fin_categories",
            "bpo_fin_cost_centers",
            "bpo_fin_suppliers",
            "bpo_fin_payment_methods",
        },
    ),
    (
        "20260326_0005",
        {
            "bpo_fin_payables",
            "bpo_fin_payable_payments",
            "bpo_fin_payable_events",
        },
    ),
    (
        "20260406_0006",
        {
            "dilmaria_pop_revisions",
            "dilmaria_pop_runs",
        },
    ),
    ("20260406_0007", {"dilmaria_pop_drafts"}),
)
REVISION_ORDER = [revision for revision, _ in SCHEMA_REVISIONS]


def _run(*args: str) -> None:
    subprocess.run(args, check=True)


def _read_current_revision(table_names: set[str]) -> str | None:
    if "alembic_version" not in table_names:
        return None
    with engine.connect() as connection:
        return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()


def _detect_existing_revision(table_names: set[str]) -> str | None:
    detected: str | None = None
    for revision, required_tables in SCHEMA_REVISIONS:
        if required_tables.issubset(table_names):
            detected = revision
    return detected


def _prepare_database() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    current_revision = _read_current_revision(table_names)
    detected_revision = _detect_existing_revision(table_names)

    if detected_revision and current_revision != detected_revision:
        print(
            "[render_start] Existing schema detected, "
            f"stamping revision {detected_revision} (current={current_revision or 'none'})",
            flush=True,
        )
        _run(sys.executable, "-m", "alembic", "stamp", detected_revision)

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
            "webapp.main:app",
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
