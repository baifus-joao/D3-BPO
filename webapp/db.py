from __future__ import annotations

from os import getenv
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def _normalize_database_url(raw_url: str) -> str:
    if raw_url.startswith("postgres://"):
        return raw_url.replace("postgres://", "postgresql+psycopg://", 1)
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return raw_url


BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DATABASE_URL = getenv("D3_DATABASE_URL") or getenv(
    "DATABASE_URL", f"sqlite:///{(BASE_DIR / 'app.db').as_posix()}"
)
DATABASE_URL = _normalize_database_url(
    RAW_DATABASE_URL
)

engine = create_engine(
    DATABASE_URL,
    future=True,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass
