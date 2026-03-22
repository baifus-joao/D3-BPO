from __future__ import annotations

import os
import subprocess
import sys

from sqlalchemy import inspect

from webapp.db import engine


MANAGED_TABLES = {"d3_users", "d3_execution_logs"}


def _run(*args: str) -> None:
    subprocess.run(args, check=True)


def _prepare_database() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    if "alembic_version" not in table_names and MANAGED_TABLES.issubset(table_names):
        _run(sys.executable, "-m", "alembic", "stamp", "head")

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
    main()
