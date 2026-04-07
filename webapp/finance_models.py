from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class BPOFinancialBankAccount(Base):
    __tablename__ = "bpo_fin_bank_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("bpo_clients.id"), nullable=False, index=True)
    bank_name: Mapped[str] = mapped_column(String(120), nullable=False)
    account_name: Mapped[str] = mapped_column(String(120), nullable=False)
    agency: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    account_number: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    pix_key: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    initial_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    client = relationship("BPOClient")
    payables: Mapped[list["BPOFinancialPayable"]] = relationship(back_populates="bank_account")
    payment_records: Mapped[list["BPOFinancialPayablePayment"]] = relationship(back_populates="bank_account")


class BPOFinancialCategory(Base):
    __tablename__ = "bpo_fin_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("bpo_clients.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="saida", index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("bpo_fin_categories.id"), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    client = relationship("BPOClient")
    parent: Mapped[BPOFinancialCategory | None] = relationship("BPOFinancialCategory", remote_side=[id])
    payables: Mapped[list["BPOFinancialPayable"]] = relationship(back_populates="category")


class BPOFinancialCostCenter(Base):
    __tablename__ = "bpo_fin_cost_centers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("bpo_clients.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    client = relationship("BPOClient")
    payables: Mapped[list["BPOFinancialPayable"]] = relationship(back_populates="cost_center")


class BPOFinancialSupplier(Base):
    __tablename__ = "bpo_fin_suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("bpo_clients.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    document: Mapped[str] = mapped_column(String(32), nullable=False, default="", index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    phone: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    client = relationship("BPOClient")
    payables: Mapped[list["BPOFinancialPayable"]] = relationship(back_populates="supplier")


class BPOFinancialPaymentMethod(Base):
    __tablename__ = "bpo_fin_payment_methods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("bpo_clients.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    client = relationship("BPOClient")
    payables: Mapped[list["BPOFinancialPayable"]] = relationship(back_populates="payment_method")


class BPOFinancialPayable(Base):
    __tablename__ = "bpo_fin_payables"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("bpo_clients.id"), nullable=False, index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("bpo_fin_suppliers.id"), nullable=True, index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("bpo_fin_categories.id"), nullable=True, index=True)
    cost_center_id: Mapped[int | None] = mapped_column(ForeignKey("bpo_fin_cost_centers.id"), nullable=True, index=True)
    payment_method_id: Mapped[int | None] = mapped_column(ForeignKey("bpo_fin_payment_methods.id"), nullable=True, index=True)
    bank_account_id: Mapped[int | None] = mapped_column(ForeignKey("bpo_fin_bank_accounts.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    document_number: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    issue_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today, index=True)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    competence_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="aberto", index=True)
    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("d3_users.id"), nullable=True, index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("d3_users.id"), nullable=True, index=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    client = relationship("BPOClient")
    supplier: Mapped[BPOFinancialSupplier | None] = relationship(back_populates="payables")
    category: Mapped[BPOFinancialCategory | None] = relationship(back_populates="payables")
    cost_center: Mapped[BPOFinancialCostCenter | None] = relationship(back_populates="payables")
    payment_method: Mapped[BPOFinancialPaymentMethod | None] = relationship(back_populates="payables")
    bank_account: Mapped[BPOFinancialBankAccount | None] = relationship(back_populates="payables")
    assigned_user = relationship("User", foreign_keys=[assigned_user_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])
    payments: Mapped[list["BPOFinancialPayablePayment"]] = relationship(back_populates="payable", cascade="all, delete-orphan")
    events: Mapped[list["BPOFinancialPayableEvent"]] = relationship(back_populates="payable", cascade="all, delete-orphan")


class BPOFinancialPayablePayment(Base):
    __tablename__ = "bpo_fin_payable_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payable_id: Mapped[int] = mapped_column(ForeignKey("bpo_fin_payables.id"), nullable=False, index=True)
    bank_account_id: Mapped[int | None] = mapped_column(ForeignKey("bpo_fin_bank_accounts.id"), nullable=True, index=True)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    reference: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("d3_users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    payable: Mapped[BPOFinancialPayable] = relationship(back_populates="payments")
    bank_account: Mapped[BPOFinancialBankAccount | None] = relationship(back_populates="payment_records")
    created_by = relationship("User")


class BPOFinancialPayableEvent(Base):
    __tablename__ = "bpo_fin_payable_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payable_id: Mapped[int] = mapped_column(ForeignKey("bpo_fin_payables.id"), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("d3_users.id"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, default="nota", index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    payable: Mapped[BPOFinancialPayable] = relationship(back_populates="events")
    user = relationship("User")
