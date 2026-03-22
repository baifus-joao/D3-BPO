"""initial schema

Revision ID: 20260322_0001
Revises: None
Create Date: 2026-03-22 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260322_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "d3_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_d3_users_email"), "d3_users", ["email"], unique=True)

    op.create_table(
        "d3_execution_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("arquivo_vendas", sa.String(length=255), nullable=False),
        sa.Column("arquivo_recebimentos", sa.String(length=255), nullable=False),
        sa.Column("arquivo_saida", sa.String(length=255), nullable=False),
        sa.Column("total_processado", sa.Integer(), nullable=False),
        sa.Column("vendas_sem_recebimento", sa.Integer(), nullable=False),
        sa.Column("duracao_ms", sa.Integer(), nullable=False),
        sa.Column("detalhe", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["d3_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_d3_execution_logs_user_id"), "d3_execution_logs", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_d3_execution_logs_user_id"), table_name="d3_execution_logs")
    op.drop_table("d3_execution_logs")
    op.drop_index(op.f("ix_d3_users_email"), table_name="d3_users")
    op.drop_table("d3_users")
