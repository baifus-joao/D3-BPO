"""finance payables for bpo clients

Revision ID: 20260326_0005
Revises: 20260326_0004
Create Date: 2026-03-26 01:10:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260326_0005"
down_revision = "20260326_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bpo_fin_payables",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("cost_center_id", sa.Integer(), nullable=True),
        sa.Column("payment_method_id", sa.Integer(), nullable=True),
        sa.Column("bank_account_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("document_number", sa.String(length=80), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("competence_date", sa.Date(), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("paid_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("assigned_user_id", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["d3_users.id"]),
        sa.ForeignKeyConstraint(["bank_account_id"], ["bpo_fin_bank_accounts.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["bpo_fin_categories.id"]),
        sa.ForeignKeyConstraint(["client_id"], ["bpo_clients.id"]),
        sa.ForeignKeyConstraint(["cost_center_id"], ["bpo_fin_cost_centers.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["d3_users.id"]),
        sa.ForeignKeyConstraint(["payment_method_id"], ["bpo_fin_payment_methods.id"]),
        sa.ForeignKeyConstraint(["supplier_id"], ["bpo_fin_suppliers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bpo_fin_payables_assigned_user_id"), "bpo_fin_payables", ["assigned_user_id"], unique=False)
    op.create_index(op.f("ix_bpo_fin_payables_bank_account_id"), "bpo_fin_payables", ["bank_account_id"], unique=False)
    op.create_index(op.f("ix_bpo_fin_payables_category_id"), "bpo_fin_payables", ["category_id"], unique=False)
    op.create_index(op.f("ix_bpo_fin_payables_client_id"), "bpo_fin_payables", ["client_id"], unique=False)
    op.create_index(op.f("ix_bpo_fin_payables_competence_date"), "bpo_fin_payables", ["competence_date"], unique=False)
    op.create_index(op.f("ix_bpo_fin_payables_cost_center_id"), "bpo_fin_payables", ["cost_center_id"], unique=False)
    op.create_index(op.f("ix_bpo_fin_payables_created_by_user_id"), "bpo_fin_payables", ["created_by_user_id"], unique=False)
    op.create_index(op.f("ix_bpo_fin_payables_due_date"), "bpo_fin_payables", ["due_date"], unique=False)
    op.create_index(op.f("ix_bpo_fin_payables_issue_date"), "bpo_fin_payables", ["issue_date"], unique=False)
    op.create_index(op.f("ix_bpo_fin_payables_payment_method_id"), "bpo_fin_payables", ["payment_method_id"], unique=False)
    op.create_index(op.f("ix_bpo_fin_payables_status"), "bpo_fin_payables", ["status"], unique=False)
    op.create_index(op.f("ix_bpo_fin_payables_supplier_id"), "bpo_fin_payables", ["supplier_id"], unique=False)

    op.create_table(
        "bpo_fin_payable_payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("payable_id", sa.Integer(), nullable=False),
        sa.Column("bank_account_id", sa.Integer(), nullable=True),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("reference", sa.String(length=120), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["bank_account_id"], ["bpo_fin_bank_accounts.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["d3_users.id"]),
        sa.ForeignKeyConstraint(["payable_id"], ["bpo_fin_payables.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bpo_fin_payable_payments_bank_account_id"), "bpo_fin_payable_payments", ["bank_account_id"], unique=False)
    op.create_index(op.f("ix_bpo_fin_payable_payments_created_by_user_id"), "bpo_fin_payable_payments", ["created_by_user_id"], unique=False)
    op.create_index(op.f("ix_bpo_fin_payable_payments_payable_id"), "bpo_fin_payable_payments", ["payable_id"], unique=False)
    op.create_index(op.f("ix_bpo_fin_payable_payments_payment_date"), "bpo_fin_payable_payments", ["payment_date"], unique=False)

    op.create_table(
        "bpo_fin_payable_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("payable_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["payable_id"], ["bpo_fin_payables.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["d3_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bpo_fin_payable_events_event_type"), "bpo_fin_payable_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_bpo_fin_payable_events_payable_id"), "bpo_fin_payable_events", ["payable_id"], unique=False)
    op.create_index(op.f("ix_bpo_fin_payable_events_user_id"), "bpo_fin_payable_events", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_bpo_fin_payable_events_user_id"), table_name="bpo_fin_payable_events")
    op.drop_index(op.f("ix_bpo_fin_payable_events_payable_id"), table_name="bpo_fin_payable_events")
    op.drop_index(op.f("ix_bpo_fin_payable_events_event_type"), table_name="bpo_fin_payable_events")
    op.drop_table("bpo_fin_payable_events")

    op.drop_index(op.f("ix_bpo_fin_payable_payments_payment_date"), table_name="bpo_fin_payable_payments")
    op.drop_index(op.f("ix_bpo_fin_payable_payments_payable_id"), table_name="bpo_fin_payable_payments")
    op.drop_index(op.f("ix_bpo_fin_payable_payments_created_by_user_id"), table_name="bpo_fin_payable_payments")
    op.drop_index(op.f("ix_bpo_fin_payable_payments_bank_account_id"), table_name="bpo_fin_payable_payments")
    op.drop_table("bpo_fin_payable_payments")

    op.drop_index(op.f("ix_bpo_fin_payables_supplier_id"), table_name="bpo_fin_payables")
    op.drop_index(op.f("ix_bpo_fin_payables_status"), table_name="bpo_fin_payables")
    op.drop_index(op.f("ix_bpo_fin_payables_payment_method_id"), table_name="bpo_fin_payables")
    op.drop_index(op.f("ix_bpo_fin_payables_issue_date"), table_name="bpo_fin_payables")
    op.drop_index(op.f("ix_bpo_fin_payables_due_date"), table_name="bpo_fin_payables")
    op.drop_index(op.f("ix_bpo_fin_payables_created_by_user_id"), table_name="bpo_fin_payables")
    op.drop_index(op.f("ix_bpo_fin_payables_cost_center_id"), table_name="bpo_fin_payables")
    op.drop_index(op.f("ix_bpo_fin_payables_competence_date"), table_name="bpo_fin_payables")
    op.drop_index(op.f("ix_bpo_fin_payables_client_id"), table_name="bpo_fin_payables")
    op.drop_index(op.f("ix_bpo_fin_payables_category_id"), table_name="bpo_fin_payables")
    op.drop_index(op.f("ix_bpo_fin_payables_bank_account_id"), table_name="bpo_fin_payables")
    op.drop_index(op.f("ix_bpo_fin_payables_assigned_user_id"), table_name="bpo_fin_payables")
    op.drop_table("bpo_fin_payables")
