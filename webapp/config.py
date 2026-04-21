from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
VALID_SESSION_SAME_SITE = {"lax", "strict", "none"}
INVALID_SESSION_DOMAIN_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _load_local_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        normalized_key = key.strip()
        if normalized_key and normalized_key not in os.environ:
            os.environ[normalized_key] = value.strip().strip('"').strip("'")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return int(raw.strip())


def _normalize_database_url(raw_url: str) -> str:
    if raw_url.startswith("postgres://"):
        return raw_url.replace("postgres://", "postgresql+psycopg://", 1)
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return raw_url


def _resolve_database_url() -> str:
    raw = os.getenv("D3_DATABASE_URL") or os.getenv(
        "DATABASE_URL",
        f"sqlite:///{(PROJECT_ROOT / 'app.db').as_posix()}",
    )
    return _normalize_database_url(raw)


def _resolve_session_secret() -> str:
    explicit_secret = os.getenv("SESSION_SECRET", "").strip()
    if explicit_secret:
        if os.getenv("RENDER") and len(explicit_secret) < 32:
            raise RuntimeError("SESSION_SECRET precisa ter pelo menos 32 caracteres em producao.")
        return explicit_secret
    if os.getenv("RENDER"):
        raise RuntimeError("Defina SESSION_SECRET antes do deploy em producao.")
    return secrets.token_urlsafe(48)


def _resolve_session_same_site(https_only: bool) -> str:
    same_site = os.getenv("SESSION_SAME_SITE", "lax").strip().lower() or "lax"
    if same_site not in VALID_SESSION_SAME_SITE:
        supported = ", ".join(sorted(VALID_SESSION_SAME_SITE))
        raise RuntimeError(f"SESSION_SAME_SITE invalido. Use um destes valores: {supported}.")
    if same_site == "none" and not https_only:
        raise RuntimeError("SESSION_SAME_SITE=none exige SESSION_HTTPS_ONLY=true.")
    return same_site


def _resolve_session_domain() -> str | None:
    raw = (os.getenv("SESSION_DOMAIN") or "").strip()
    if not raw:
        return None

    candidate = raw
    if "://" in candidate:
        candidate = urlsplit(candidate).hostname or ""
    elif any(token in candidate for token in "/?#"):
        candidate = urlsplit(f"//{candidate}", scheme="https").hostname or ""
    else:
        candidate = candidate.split(":", 1)[0]

    normalized = candidate.strip().strip(".").lower()
    if not normalized or normalized in INVALID_SESSION_DOMAIN_HOSTS:
        return None
    return normalized


def _resolve_log_file() -> Path | None:
    raw = os.getenv("D3_LOG_FILE", "").strip()
    if not raw:
        return None
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


@dataclass(frozen=True, slots=True)
class Settings:
    base_dir: Path
    project_root: Path
    database_url: str
    session_secret: str
    session_domain: str | None
    session_https_only: bool
    session_same_site: str
    session_max_age_seconds: int
    login_max_attempts: int
    login_window_seconds: int
    login_lock_seconds: int
    download_ttl_seconds: int
    bootstrap_admin_name: str
    bootstrap_admin_email: str
    bootstrap_admin_password: str
    openai_layout_model: str
    log_level: str
    log_file: Path | None


@lru_cache
def get_settings() -> Settings:
    _load_local_env()
    https_only = _env_bool("SESSION_HTTPS_ONLY", False)
    return Settings(
        base_dir=BASE_DIR,
        project_root=PROJECT_ROOT,
        database_url=_resolve_database_url(),
        session_secret=_resolve_session_secret(),
        session_domain=_resolve_session_domain(),
        session_https_only=https_only,
        session_same_site=_resolve_session_same_site(https_only),
        session_max_age_seconds=_env_int("SESSION_MAX_AGE_SECONDS", 60 * 60 * 8),
        login_max_attempts=_env_int("LOGIN_MAX_ATTEMPTS", 5),
        login_window_seconds=_env_int("LOGIN_WINDOW_SECONDS", 15 * 60),
        login_lock_seconds=_env_int("LOGIN_LOCK_SECONDS", 10 * 60),
        download_ttl_seconds=_env_int("DOWNLOAD_TTL_SECONDS", 60 * 60),
        bootstrap_admin_name=os.getenv("D3_BOOTSTRAP_ADMIN_NAME", "Administrador D3").strip(),
        bootstrap_admin_email=os.getenv("D3_BOOTSTRAP_ADMIN_EMAIL", "admin@d3financeiro.local").strip().lower(),
        bootstrap_admin_password=os.getenv("D3_BOOTSTRAP_ADMIN_PASSWORD", "Admin123!").strip(),
        openai_layout_model=os.getenv("OPENAI_LAYOUT_MODEL", "").strip(),
        log_level=os.getenv("D3_LOG_LEVEL", "INFO").strip().upper() or "INFO",
        log_file=_resolve_log_file(),
    )


settings = get_settings()
