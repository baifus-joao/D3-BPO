from __future__ import annotations

import importlib
import sys


def _reload_config():
    for name in [module for module in sys.modules if module.startswith("webapp.config")]:
        sys.modules.pop(name, None)
    return importlib.import_module("webapp.config")


def test_session_domain_uses_hostname_from_url(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_DOMAIN", "https://painel-d3.onrender.com/login")

    config = _reload_config()

    assert config.get_settings().session_domain == "painel-d3.onrender.com"


def test_session_domain_ignores_localhost(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_DOMAIN", "localhost")

    config = _reload_config()

    assert config.get_settings().session_domain is None
