from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from webapp.db import Base
from webapp.time_utils import utcnow


class DilmariaPopRevision(Base):
    __tablename__ = "dilmaria_pop_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    current_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=-1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )


class DilmariaPopRun(Base):
    __tablename__ = "dilmaria_pop_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("d3_users.id"), nullable=False, index=True)
    pop_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    codigo: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    revisao: Mapped[str] = mapped_column(String(40), nullable=False)
    structure_key: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    structure_name: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    payload_snapshot: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    user = relationship("User")


class DilmariaPopDraft(Base):
    __tablename__ = "dilmaria_pop_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("d3_users.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    titulo: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    codigo: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    structure_key: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    payload_snapshot: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    user = relationship("User")
