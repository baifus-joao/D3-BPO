"""Compatibility shim for local tooling that still imports `main:app`.

The canonical ASGI entrypoint for the project is `webapp.main:app`.
"""

from webapp.main import app
