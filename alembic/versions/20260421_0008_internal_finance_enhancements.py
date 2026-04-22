"""internal finance enhancements

Revision ID: 20260421_0008
Revises: 20260406_0007
Create Date: 2026-04-21 20:20:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260421_0008"
down_revision = "20260406_0007"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = "d3_financial_transactions"

    if not _has_column(inspector, table_name, "interested_party"):
        op.add_column(
            table_name,
            sa.Column("interested_party", sa.String(length=160), nullable=False, server_default=""),
        )
    if not _has_column(inspector, table_name, "entry_mode"):
        op.add_column(
            table_name,
            sa.Column("entry_mode", sa.String(length=20), nullable=False, server_default="avista"),
        )
    if not _has_column(inspector, table_name, "group_key"):
        op.add_column(
            table_name,
            sa.Column("group_key", sa.String(length=64), nullable=True),
        )
    if not _has_column(inspector, table_name, "installment_number"):
        op.add_column(
            table_name,
            sa.Column("installment_number", sa.Integer(), nullable=True),
        )
    if not _has_column(inspector, table_name, "installment_total"):
        op.add_column(
            table_name,
            sa.Column("installment_total", sa.Integer(), nullable=True),
        )
    if not _has_column(inspector, table_name, "projection_label"):
        op.add_column(
            table_name,
            sa.Column("projection_label", sa.String(length=120), nullable=False, server_default=""),
        )
    if not _has_column(inspector, table_name, "projection_start"):
        op.add_column(
            table_name,
            sa.Column("projection_start", sa.Date(), nullable=True),
        )
    if not _has_column(inspector, table_name, "projection_end"):
        op.add_column(
            table_name,
            sa.Column("projection_end", sa.Date(), nullable=True),
        )

    inspector = sa.inspect(bind)
    if not _has_index(inspector, table_name, op.f("ix_d3_financial_transactions_interested_party")):
        op.create_index(
            op.f("ix_d3_financial_transactions_interested_party"),
            table_name,
            ["interested_party"],
            unique=False,
        )
    if not _has_index(inspector, table_name, op.f("ix_d3_financial_transactions_entry_mode")):
        op.create_index(
            op.f("ix_d3_financial_transactions_entry_mode"),
            table_name,
            ["entry_mode"],
            unique=False,
        )
    if not _has_index(inspector, table_name, op.f("ix_d3_financial_transactions_group_key")):
        op.create_index(
            op.f("ix_d3_financial_transactions_group_key"),
            table_name,
            ["group_key"],
            unique=False,
        )

def downgrade() -> None:
    op.drop_index(op.f("ix_d3_financial_transactions_group_key"), table_name="d3_financial_transactions")
    op.drop_index(op.f("ix_d3_financial_transactions_entry_mode"), table_name="d3_financial_transactions")
    op.drop_index(op.f("ix_d3_financial_transactions_interested_party"), table_name="d3_financial_transactions")

    op.drop_column("d3_financial_transactions", "projection_end")
    op.drop_column("d3_financial_transactions", "projection_start")
    op.drop_column("d3_financial_transactions", "projection_label")
    op.drop_column("d3_financial_transactions", "installment_total")
    op.drop_column("d3_financial_transactions", "installment_number")
    op.drop_column("d3_financial_transactions", "group_key")
    op.drop_column("d3_financial_transactions", "entry_mode")
    op.drop_column("d3_financial_transactions", "interested_party")
