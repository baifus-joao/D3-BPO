from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient


def _clear_webapp_modules() -> None:
    for name in [module for module in sys.modules if module.startswith("webapp")]:
        sys.modules.pop(name, None)


def _upgrade_test_database(database_url: str) -> None:
    alembic_config = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    alembic_config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(alembic_config, "head")


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "test_app.db"
    monkeypatch.setenv("D3_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("D3_BOOTSTRAP_ADMIN_NAME", "Admin Teste")
    monkeypatch.setenv("D3_BOOTSTRAP_ADMIN_EMAIL", "admin@teste.local")
    monkeypatch.setenv("D3_BOOTSTRAP_ADMIN_PASSWORD", "Admin123!")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    _clear_webapp_modules()
    _upgrade_test_database(f"sqlite:///{db_path.as_posix()}")
    _clear_webapp_modules()
    main_module = importlib.import_module("webapp.main")

    with TestClient(main_module.app) as test_client:
        yield test_client


@pytest.fixture
def authenticated_client(client: TestClient) -> TestClient:
    login_page = client.get("/login")
    assert login_page.status_code == 200
    match = re.search(r'name="csrf_token" value="([^"]+)"', login_page.text)
    assert match, "csrf token nao encontrado na pagina de login"
    csrf_token = match.group(1)
    response = client.post(
        "/login",
        data={
            "csrf_token": csrf_token,
            "email": "admin@teste.local",
            "password": "Admin123!",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    client.headers.update({"X-CSRF-Token": csrf_token})
    return client
