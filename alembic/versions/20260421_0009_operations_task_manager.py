"""operations task manager structure

Revision ID: 20260421_0009
Revises: 20260421_0008
Create Date: 2026-04-21 22:10:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260421_0009"
down_revision = "20260421_0008"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_column(inspector, "bpo_clients", "contracted_plan"):
        op.add_column("bpo_clients", sa.Column("contracted_plan", sa.String(length=120), nullable=False, server_default=""))
    if not _has_column(inspector, "bpo_clients", "sla_deadline_day"):
        op.add_column("bpo_clients", sa.Column("sla_deadline_day", sa.Integer(), nullable=True))
    if not _has_column(inspector, "bpo_clients", "team_label"):
        op.add_column("bpo_clients", sa.Column("team_label", sa.String(length=120), nullable=False, server_default=""))

    inspector = sa.inspect(bind)
    if not _has_table(inspector, "bpo_projects"):
        op.create_table(
            "bpo_projects",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("client_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("project_type", sa.String(length=60), nullable=False, server_default="rotina_mensal"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="ativo"),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("start_date", sa.Date(), nullable=True),
            sa.Column("end_date", sa.Date(), nullable=True),
            sa.Column("responsible_user_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["client_id"], ["bpo_clients.id"]),
            sa.ForeignKeyConstraint(["responsible_user_id"], ["d3_users.id"]),
        )
        op.create_index(op.f("ix_bpo_projects_client_id"), "bpo_projects", ["client_id"], unique=False)
        op.create_index(op.f("ix_bpo_projects_project_type"), "bpo_projects", ["project_type"], unique=False)
        op.create_index(op.f("ix_bpo_projects_responsible_user_id"), "bpo_projects", ["responsible_user_id"], unique=False)
        op.create_index(op.f("ix_bpo_projects_status"), "bpo_projects", ["status"], unique=False)

    inspector = sa.inspect(bind)
    if not _has_column(inspector, "bpo_tasks", "project_id"):
        op.add_column("bpo_tasks", sa.Column("project_id", sa.Integer(), nullable=True))
    inspector = sa.inspect(bind)
    if not _has_index(inspector, "bpo_tasks", op.f("ix_bpo_tasks_project_id")):
        op.create_index(op.f("ix_bpo_tasks_project_id"), "bpo_tasks", ["project_id"], unique=False)

    inspector = sa.inspect(bind)
    if not _has_table(inspector, "bpo_demands"):
        op.create_table(
            "bpo_demands",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("client_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=True),
            sa.Column("title", sa.String(length=160), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("source", sa.String(length=30), nullable=False, server_default="manual"),
            sa.Column("demand_type", sa.String(length=40), nullable=False, server_default="operacional"),
            sa.Column("priority", sa.String(length=20), nullable=False, server_default="normal"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="aberta"),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("responsible_user_id", sa.Integer(), nullable=True),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            sa.Column("converted_task_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["client_id"], ["bpo_clients.id"]),
            sa.ForeignKeyConstraint(["project_id"], ["bpo_projects.id"]),
            sa.ForeignKeyConstraint(["responsible_user_id"], ["d3_users.id"]),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["d3_users.id"]),
            sa.ForeignKeyConstraint(["converted_task_id"], ["bpo_tasks.id"]),
        )
        op.create_index(op.f("ix_bpo_demands_client_id"), "bpo_demands", ["client_id"], unique=False)
        op.create_index(op.f("ix_bpo_demands_project_id"), "bpo_demands", ["project_id"], unique=False)
        op.create_index(op.f("ix_bpo_demands_source"), "bpo_demands", ["source"], unique=False)
        op.create_index(op.f("ix_bpo_demands_demand_type"), "bpo_demands", ["demand_type"], unique=False)
        op.create_index(op.f("ix_bpo_demands_priority"), "bpo_demands", ["priority"], unique=False)
        op.create_index(op.f("ix_bpo_demands_status"), "bpo_demands", ["status"], unique=False)
        op.create_index(op.f("ix_bpo_demands_responsible_user_id"), "bpo_demands", ["responsible_user_id"], unique=False)
        op.create_index(op.f("ix_bpo_demands_created_by_user_id"), "bpo_demands", ["created_by_user_id"], unique=False)
        op.create_index(op.f("ix_bpo_demands_converted_task_id"), "bpo_demands", ["converted_task_id"], unique=False)

    inspector = sa.inspect(bind)
    if not _has_table(inspector, "bpo_task_time_entries"):
        op.create_table(
            "bpo_task_time_entries",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("task_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("ended_at", sa.DateTime(), nullable=True),
            sa.Column("duration_seconds", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("note", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["task_id"], ["bpo_tasks.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["d3_users.id"]),
        )
        op.create_index(op.f("ix_bpo_task_time_entries_task_id"), "bpo_task_time_entries", ["task_id"], unique=False)
        op.create_index(op.f("ix_bpo_task_time_entries_user_id"), "bpo_task_time_entries", ["user_id"], unique=False)
        op.create_index(op.f("ix_bpo_task_time_entries_started_at"), "bpo_task_time_entries", ["started_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_bpo_task_time_entries_started_at"), table_name="bpo_task_time_entries")
    op.drop_index(op.f("ix_bpo_task_time_entries_user_id"), table_name="bpo_task_time_entries")
    op.drop_index(op.f("ix_bpo_task_time_entries_task_id"), table_name="bpo_task_time_entries")
    op.drop_table("bpo_task_time_entries")

    op.drop_index(op.f("ix_bpo_demands_converted_task_id"), table_name="bpo_demands")
    op.drop_index(op.f("ix_bpo_demands_created_by_user_id"), table_name="bpo_demands")
    op.drop_index(op.f("ix_bpo_demands_responsible_user_id"), table_name="bpo_demands")
    op.drop_index(op.f("ix_bpo_demands_status"), table_name="bpo_demands")
    op.drop_index(op.f("ix_bpo_demands_priority"), table_name="bpo_demands")
    op.drop_index(op.f("ix_bpo_demands_demand_type"), table_name="bpo_demands")
    op.drop_index(op.f("ix_bpo_demands_source"), table_name="bpo_demands")
    op.drop_index(op.f("ix_bpo_demands_project_id"), table_name="bpo_demands")
    op.drop_index(op.f("ix_bpo_demands_client_id"), table_name="bpo_demands")
    op.drop_table("bpo_demands")

    op.drop_index(op.f("ix_bpo_tasks_project_id"), table_name="bpo_tasks")
    op.drop_column("bpo_tasks", "project_id")

    op.drop_index(op.f("ix_bpo_projects_status"), table_name="bpo_projects")
    op.drop_index(op.f("ix_bpo_projects_responsible_user_id"), table_name="bpo_projects")
    op.drop_index(op.f("ix_bpo_projects_project_type"), table_name="bpo_projects")
    op.drop_index(op.f("ix_bpo_projects_client_id"), table_name="bpo_projects")
    op.drop_table("bpo_projects")

    op.drop_column("bpo_clients", "team_label")
    op.drop_column("bpo_clients", "sla_deadline_day")
    op.drop_column("bpo_clients", "contracted_plan")
