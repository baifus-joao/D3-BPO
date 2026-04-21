from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .time_utils import utcnow


class User(Base):
    __tablename__ = "d3_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="operacional")
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    executions: Mapped[list["ExecutionLog"]] = relationship(back_populates="user")
    created_transactions: Mapped[list["FinancialTransaction"]] = relationship(back_populates="created_by")


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
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    user: Mapped[User] = relationship(back_populates="executions")


class Store(Base):
    __tablename__ = "d3_stores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    transactions: Mapped[list["FinancialTransaction"]] = relationship(back_populates="store")


class BankAccount(Base):
    __tablename__ = "d3_bank_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    bank_name: Mapped[str] = mapped_column(String(120), nullable=False)
    branch: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    account_number: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    transactions: Mapped[list["FinancialTransaction"]] = relationship(back_populates="bank_account")


class FinancialCategory(Base):
    __tablename__ = "d3_financial_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False, default="ENTRADA")
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="#22ffc4")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    transactions: Mapped[list["FinancialTransaction"]] = relationship(back_populates="category")


class PaymentMethod(Base):
    __tablename__ = "d3_payment_methods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    transactions: Mapped[list["FinancialTransaction"]] = relationship(back_populates="payment_method")


class FinancialTransaction(Base):
    __tablename__ = "d3_financial_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today, index=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("d3_financial_categories.id"), nullable=True, index=True)
    subcategory: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    payment_method_id: Mapped[int | None] = mapped_column(ForeignKey("d3_payment_methods.id"), nullable=True, index=True)
    bank_account_id: Mapped[int | None] = mapped_column(ForeignKey("d3_bank_accounts.id"), nullable=True, index=True)
    store_id: Mapped[int | None] = mapped_column(ForeignKey("d3_stores.id"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="manual", index=True)
    source_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="", index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="previsto", index=True)
    planned_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    realized_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("d3_users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    category: Mapped[FinancialCategory | None] = relationship(back_populates="transactions")
    payment_method: Mapped[PaymentMethod | None] = relationship(back_populates="transactions")
    bank_account: Mapped[BankAccount | None] = relationship(back_populates="transactions")
    store: Mapped[Store | None] = relationship(back_populates="transactions")
    created_by: Mapped[User | None] = relationship(back_populates="created_transactions")
