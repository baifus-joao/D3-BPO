from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .time_utils import utcnow


class BPOClient(Base):
    __tablename__ = "bpo_clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    legal_name: Mapped[str] = mapped_column(String(160), nullable=False)
    trade_name: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    document: Mapped[str] = mapped_column(String(32), nullable=False, default="", index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ativo", index=True)
    segment: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    responsible_user_id: Mapped[int | None] = mapped_column(ForeignKey("d3_users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    responsible_user = relationship("User")
    contacts: Mapped[list["BPOClientContact"]] = relationship(back_populates="client", cascade="all, delete-orphan")
    routines: Mapped[list["BPORecurringRoutine"]] = relationship(back_populates="client", cascade="all, delete-orphan")
    tasks: Mapped[list["BPOTask"]] = relationship(back_populates="client", cascade="all, delete-orphan")
    conciliation_runs: Mapped[list["BPOConciliationRun"]] = relationship(back_populates="client", cascade="all, delete-orphan")


class BPOClientContact(Base):
    __tablename__ = "bpo_client_contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("bpo_clients.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    phone: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    role: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    client: Mapped[BPOClient] = relationship(back_populates="contacts")


class BPOTaskTemplate(Base):
    __tablename__ = "bpo_task_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    service_type: Mapped[str] = mapped_column(String(40), nullable=False, default="operacional", index=True)
    default_sla_days: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    requires_competence: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    tasks: Mapped[list["BPOTask"]] = relationship(back_populates="task_template")
    routines: Mapped[list["BPORecurringRoutine"]] = relationship(back_populates="task_template")


class BPORecurringRoutine(Base):
    __tablename__ = "bpo_recurring_routines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("bpo_clients.id"), nullable=False, index=True)
    task_template_id: Mapped[int] = mapped_column(ForeignKey("bpo_task_templates.id"), nullable=False, index=True)
    frequency: Mapped[str] = mapped_column(String(20), nullable=False, default="monthly")
    day_of_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    default_assignee_user_id: Mapped[int | None] = mapped_column(ForeignKey("d3_users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    client: Mapped[BPOClient] = relationship(back_populates="routines")
    task_template: Mapped[BPOTaskTemplate] = relationship(back_populates="routines")
    default_assignee = relationship("User")


class BPOTask(Base):
    __tablename__ = "bpo_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("bpo_clients.id"), nullable=False, index=True)
    task_template_id: Mapped[int | None] = mapped_column(ForeignKey("bpo_task_templates.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pendente", index=True)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal", index=True)
    competence_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("d3_users.id"), nullable=True, index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("d3_users.id"), nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    client: Mapped[BPOClient] = relationship(back_populates="tasks")
    task_template: Mapped[BPOTaskTemplate | None] = relationship(back_populates="tasks")
    assigned_user = relationship("User", foreign_keys=[assigned_user_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])
    events: Mapped[list["BPOTaskEvent"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    conciliation_runs: Mapped[list["BPOConciliationRun"]] = relationship(back_populates="task")


class BPOTaskEvent(Base):
    __tablename__ = "bpo_task_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("bpo_tasks.id"), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("d3_users.id"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, default="nota")
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    task: Mapped[BPOTask] = relationship(back_populates="events")
    user = relationship("User")


class BPOConciliationRun(Base):
    __tablename__ = "bpo_conciliation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("bpo_clients.id"), nullable=False, index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("bpo_tasks.id"), nullable=True, index=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="concluida", index=True)
    uploaded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("d3_users.id"), nullable=True, index=True)
    arquivo_vendas: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    arquivo_recebimentos: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    arquivo_saida: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    total_vendas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_recebimentos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_divergencias: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duracao_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    client: Mapped[BPOClient] = relationship(back_populates="conciliation_runs")
    task: Mapped[BPOTask | None] = relationship(back_populates="conciliation_runs")
    uploaded_by = relationship("User")
    items: Mapped[list["BPOConciliationItem"]] = relationship(back_populates="conciliation_run", cascade="all, delete-orphan")


class BPOConciliationItem(Base):
    __tablename__ = "bpo_conciliation_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conciliation_run_id: Mapped[int] = mapped_column(ForeignKey("bpo_conciliation_runs.id"), nullable=False, index=True)
    item_type: Mapped[str] = mapped_column(String(40), nullable=False, default="divergencia", index=True)
    reference_key: Mapped[str] = mapped_column(String(255), nullable=False, default="", index=True)
    sale_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    paid_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    gross_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    net_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    difference_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="aberto", index=True)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    conciliation_run: Mapped[BPOConciliationRun] = relationship(back_populates="items")
