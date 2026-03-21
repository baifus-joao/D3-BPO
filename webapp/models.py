from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class User(Base):
    __tablename__ = "d3_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="colaborador")
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    executions: Mapped[list["ExecutionLog"]] = relationship(back_populates="user")


class ExecutionLog(Base):
    __tablename__ = "d3_execution_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("d3_users.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    arquivo_vendas: Mapped[str] = mapped_column(String(255), nullable=False)
    arquivo_recebimentos: Mapped[str] = mapped_column(String(255), nullable=False)
    arquivo_saida: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    total_processado: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vendas_sem_recebimento: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duracao_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    detalhe: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    user: Mapped[User] = relationship(back_populates="executions")
