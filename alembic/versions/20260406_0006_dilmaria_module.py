"""dilmaria module tables

Revision ID: 20260406_0006
Revises: 20260326_0005
Create Date: 2026-04-06 10:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260406_0006"
down_revision = "20260326_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dilmaria_pop_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=120), nullable=False),
        sa.Column("current_revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_dilmaria_pop_revisions_codigo"),
        "dilmaria_pop_revisions",
        ["codigo"],
        unique=True,
    )

    op.create_table(
        "dilmaria_pop_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("pop_id", sa.String(length=64), nullable=False),
        sa.Column("titulo", sa.String(length=255), nullable=False),
        sa.Column("codigo", sa.String(length=120), nullable=False),
        sa.Column("revisao", sa.String(length=40), nullable=False),
        sa.Column("structure_key", sa.String(length=120), nullable=False),
        sa.Column("structure_name", sa.String(length=160), nullable=False),
        sa.Column("payload_snapshot", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["d3_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_dilmaria_pop_runs_codigo"), "dilmaria_pop_runs", ["codigo"], unique=False)
    op.create_index(op.f("ix_dilmaria_pop_runs_pop_id"), "dilmaria_pop_runs", ["pop_id"], unique=False)
    op.create_index(op.f("ix_dilmaria_pop_runs_user_id"), "dilmaria_pop_runs", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_dilmaria_pop_runs_user_id"), table_name="dilmaria_pop_runs")
    op.drop_index(op.f("ix_dilmaria_pop_runs_pop_id"), table_name="dilmaria_pop_runs")
    op.drop_index(op.f("ix_dilmaria_pop_runs_codigo"), table_name="dilmaria_pop_runs")
    op.drop_table("dilmaria_pop_runs")

    op.drop_index(op.f("ix_dilmaria_pop_revisions_codigo"), table_name="dilmaria_pop_revisions")
    op.drop_table("dilmaria_pop_revisions")
