"""erp core

Revision ID: 20260322_0002
Revises: 20260322_0001
Create Date: 2026-03-22 01:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260322_0002"
down_revision = "20260322_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE d3_users
        SET role = 'operacional'
        WHERE role = 'colaborador'
        """
    )

    op.create_table(
        "d3_stores",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_d3_stores_code"), "d3_stores", ["code"], unique=True)

    op.create_table(
        "d3_bank_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("bank_name", sa.String(length=120), nullable=False),
        sa.Column("branch", sa.String(length=20), nullable=False),
        sa.Column("account_number", sa.String(length=40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "d3_financial_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("color", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "d3_payment_methods",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_d3_payment_methods_code"), "d3_payment_methods", ["code"], unique=True)

    op.create_table(
        "d3_financial_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("subcategory", sa.String(length=120), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("payment_method_id", sa.Integer(), nullable=True),
        sa.Column("bank_account_id", sa.Integer(), nullable=True),
        sa.Column("store_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("source_reference", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("planned_date", sa.Date(), nullable=True),
        sa.Column("realized_date", sa.Date(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["bank_account_id"], ["d3_bank_accounts.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["d3_financial_categories.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["d3_users.id"]),
        sa.ForeignKeyConstraint(["payment_method_id"], ["d3_payment_methods.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["d3_stores.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(op.f("ix_d3_financial_transactions_bank_account_id"), "d3_financial_transactions", ["bank_account_id"], unique=False)
    op.create_index(op.f("ix_d3_financial_transactions_category_id"), "d3_financial_transactions", ["category_id"], unique=False)
    op.create_index(op.f("ix_d3_financial_transactions_created_by_user_id"), "d3_financial_transactions", ["created_by_user_id"], unique=False)
    op.create_index(op.f("ix_d3_financial_transactions_payment_method_id"), "d3_financial_transactions", ["payment_method_id"], unique=False)
    op.create_index(op.f("ix_d3_financial_transactions_planned_date"), "d3_financial_transactions", ["planned_date"], unique=False)
    op.create_index(op.f("ix_d3_financial_transactions_realized_date"), "d3_financial_transactions", ["realized_date"], unique=False)
    op.create_index(op.f("ix_d3_financial_transactions_source"), "d3_financial_transactions", ["source"], unique=False)
    op.create_index(op.f("ix_d3_financial_transactions_source_reference"), "d3_financial_transactions", ["source_reference"], unique=False)
    op.create_index(op.f("ix_d3_financial_transactions_status"), "d3_financial_transactions", ["status"], unique=False)
    op.create_index(op.f("ix_d3_financial_transactions_store_id"), "d3_financial_transactions", ["store_id"], unique=False)
    op.create_index(op.f("ix_d3_financial_transactions_transaction_date"), "d3_financial_transactions", ["transaction_date"], unique=False)
    op.create_index(op.f("ix_d3_financial_transactions_type"), "d3_financial_transactions", ["type"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_d3_financial_transactions_type"), table_name="d3_financial_transactions")
    op.drop_index(op.f("ix_d3_financial_transactions_transaction_date"), table_name="d3_financial_transactions")
    op.drop_index(op.f("ix_d3_financial_transactions_store_id"), table_name="d3_financial_transactions")
    op.drop_index(op.f("ix_d3_financial_transactions_status"), table_name="d3_financial_transactions")
    op.drop_index(op.f("ix_d3_financial_transactions_source_reference"), table_name="d3_financial_transactions")
    op.drop_index(op.f("ix_d3_financial_transactions_source"), table_name="d3_financial_transactions")
    op.drop_index(op.f("ix_d3_financial_transactions_realized_date"), table_name="d3_financial_transactions")
    op.drop_index(op.f("ix_d3_financial_transactions_planned_date"), table_name="d3_financial_transactions")
    op.drop_index(op.f("ix_d3_financial_transactions_payment_method_id"), table_name="d3_financial_transactions")
    op.drop_index(op.f("ix_d3_financial_transactions_created_by_user_id"), table_name="d3_financial_transactions")
    op.drop_index(op.f("ix_d3_financial_transactions_category_id"), table_name="d3_financial_transactions")
    op.drop_index(op.f("ix_d3_financial_transactions_bank_account_id"), table_name="d3_financial_transactions")
    op.drop_table("d3_financial_transactions")

    op.drop_index(op.f("ix_d3_payment_methods_code"), table_name="d3_payment_methods")
    op.drop_table("d3_payment_methods")

    op.drop_table("d3_financial_categories")
    op.drop_table("d3_bank_accounts")

    op.drop_index(op.f("ix_d3_stores_code"), table_name="d3_stores")
    op.drop_table("d3_stores")
