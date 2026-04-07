"""finance base for bpo clients

Revision ID: 20260326_0004
Revises: 20260326_0003
Create Date: 2026-03-26 00:30:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260326_0004"
down_revision = "20260326_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bpo_fin_bank_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("bank_name", sa.String(length=120), nullable=False),
        sa.Column("account_name", sa.String(length=120), nullable=False),
        sa.Column("agency", sa.String(length=20), nullable=False),
        sa.Column("account_number", sa.String(length=40), nullable=False),
        sa.Column("pix_key", sa.String(length=120), nullable=False),
        sa.Column("initial_balance", sa.Numeric(14, 2), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["bpo_clients.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bpo_fin_bank_accounts_client_id"), "bpo_fin_bank_accounts", ["client_id"], unique=False)
    op.create_index(op.f("ix_bpo_fin_bank_accounts_is_active"), "bpo_fin_bank_accounts", ["is_active"], unique=False)

    op.create_table(
        "bpo_fin_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["bpo_clients.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["bpo_fin_categories.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id", "name", "kind", name="uq_bpo_fin_categories_client_name_kind"),
    )
    op.create_index(op.f("ix_bpo_fin_categories_client_id"), "bpo_fin_categories", ["client_id"], unique=False)
    op.create_index(op.f("ix_bpo_fin_categories_is_active"), "bpo_fin_categories", ["is_active"], unique=False)
    op.create_index(op.f("ix_bpo_fin_categories_kind"), "bpo_fin_categories", ["kind"], unique=False)
    op.create_index(op.f("ix_bpo_fin_categories_parent_id"), "bpo_fin_categories", ["parent_id"], unique=False)

    op.create_table(
        "bpo_fin_cost_centers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["bpo_clients.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id", "name", name="uq_bpo_fin_cost_centers_client_name"),
    )
    op.create_index(op.f("ix_bpo_fin_cost_centers_client_id"), "bpo_fin_cost_centers", ["client_id"], unique=False)
    op.create_index(op.f("ix_bpo_fin_cost_centers_is_active"), "bpo_fin_cost_centers", ["is_active"], unique=False)

    op.create_table(
        "bpo_fin_suppliers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("document", sa.String(length=32), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["bpo_clients.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id", "name", name="uq_bpo_fin_suppliers_client_name"),
    )
    op.create_index(op.f("ix_bpo_fin_suppliers_client_id"), "bpo_fin_suppliers", ["client_id"], unique=False)
    op.create_index(op.f("ix_bpo_fin_suppliers_document"), "bpo_fin_suppliers", ["document"], unique=False)
    op.create_index(op.f("ix_bpo_fin_suppliers_is_active"), "bpo_fin_suppliers", ["is_active"], unique=False)

    op.create_table(
        "bpo_fin_payment_methods",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["bpo_clients.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id", "name", name="uq_bpo_fin_payment_methods_client_name"),
    )
    op.create_index(op.f("ix_bpo_fin_payment_methods_client_id"), "bpo_fin_payment_methods", ["client_id"], unique=False)
    op.create_index(op.f("ix_bpo_fin_payment_methods_is_active"), "bpo_fin_payment_methods", ["is_active"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_bpo_fin_payment_methods_is_active"), table_name="bpo_fin_payment_methods")
    op.drop_index(op.f("ix_bpo_fin_payment_methods_client_id"), table_name="bpo_fin_payment_methods")
    op.drop_table("bpo_fin_payment_methods")

    op.drop_index(op.f("ix_bpo_fin_suppliers_is_active"), table_name="bpo_fin_suppliers")
    op.drop_index(op.f("ix_bpo_fin_suppliers_document"), table_name="bpo_fin_suppliers")
    op.drop_index(op.f("ix_bpo_fin_suppliers_client_id"), table_name="bpo_fin_suppliers")
    op.drop_table("bpo_fin_suppliers")

    op.drop_index(op.f("ix_bpo_fin_cost_centers_is_active"), table_name="bpo_fin_cost_centers")
    op.drop_index(op.f("ix_bpo_fin_cost_centers_client_id"), table_name="bpo_fin_cost_centers")
    op.drop_table("bpo_fin_cost_centers")

    op.drop_index(op.f("ix_bpo_fin_categories_parent_id"), table_name="bpo_fin_categories")
    op.drop_index(op.f("ix_bpo_fin_categories_kind"), table_name="bpo_fin_categories")
    op.drop_index(op.f("ix_bpo_fin_categories_is_active"), table_name="bpo_fin_categories")
    op.drop_index(op.f("ix_bpo_fin_categories_client_id"), table_name="bpo_fin_categories")
    op.drop_table("bpo_fin_categories")

    op.drop_index(op.f("ix_bpo_fin_bank_accounts_is_active"), table_name="bpo_fin_bank_accounts")
    op.drop_index(op.f("ix_bpo_fin_bank_accounts_client_id"), table_name="bpo_fin_bank_accounts")
    op.drop_table("bpo_fin_bank_accounts")
