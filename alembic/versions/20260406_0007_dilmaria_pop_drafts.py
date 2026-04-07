"""dilmaria draft persistence

Revision ID: 20260406_0007
Revises: 20260406_0006
Create Date: 2026-04-06 19:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260406_0007"
down_revision = "20260406_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dilmaria_pop_drafts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("titulo", sa.String(length=255), nullable=False),
        sa.Column("codigo", sa.String(length=120), nullable=False),
        sa.Column("structure_key", sa.String(length=120), nullable=False),
        sa.Column("payload_snapshot", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["d3_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_dilmaria_pop_drafts_user_id"),
        "dilmaria_pop_drafts",
        ["user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_dilmaria_pop_drafts_user_id"), table_name="dilmaria_pop_drafts")
    op.drop_table("dilmaria_pop_drafts")
