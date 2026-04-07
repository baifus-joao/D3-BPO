"""bpo phase 1

Revision ID: 20260326_0003
Revises: 20260322_0002
Create Date: 2026-03-26 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260326_0003"
down_revision = "20260322_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bpo_clients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("legal_name", sa.String(length=160), nullable=False),
        sa.Column("trade_name", sa.String(length=160), nullable=False),
        sa.Column("document", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("segment", sa.String(length=80), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("responsible_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["responsible_user_id"], ["d3_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bpo_clients_document"), "bpo_clients", ["document"], unique=False)
    op.create_index(op.f("ix_bpo_clients_responsible_user_id"), "bpo_clients", ["responsible_user_id"], unique=False)
    op.create_index(op.f("ix_bpo_clients_status"), "bpo_clients", ["status"], unique=False)

    op.create_table(
        "bpo_task_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("service_type", sa.String(length=40), nullable=False),
        sa.Column("default_sla_days", sa.Integer(), nullable=False),
        sa.Column("requires_competence", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_bpo_task_templates_service_type"), "bpo_task_templates", ["service_type"], unique=False)

    op.create_table(
        "bpo_client_contacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=False),
        sa.Column("role", sa.String(length=80), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["bpo_clients.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bpo_client_contacts_client_id"), "bpo_client_contacts", ["client_id"], unique=False)

    op.create_table(
        "bpo_recurring_routines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("task_template_id", sa.Integer(), nullable=False),
        sa.Column("frequency", sa.String(length=20), nullable=False),
        sa.Column("day_of_month", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("default_assignee_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["bpo_clients.id"]),
        sa.ForeignKeyConstraint(["default_assignee_user_id"], ["d3_users.id"]),
        sa.ForeignKeyConstraint(["task_template_id"], ["bpo_task_templates.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bpo_recurring_routines_client_id"), "bpo_recurring_routines", ["client_id"], unique=False)
    op.create_index(op.f("ix_bpo_recurring_routines_default_assignee_user_id"), "bpo_recurring_routines", ["default_assignee_user_id"], unique=False)
    op.create_index(op.f("ix_bpo_recurring_routines_task_template_id"), "bpo_recurring_routines", ["task_template_id"], unique=False)

    op.create_table(
        "bpo_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("task_template_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("competence_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("assigned_user_id", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["d3_users.id"]),
        sa.ForeignKeyConstraint(["client_id"], ["bpo_clients.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["d3_users.id"]),
        sa.ForeignKeyConstraint(["task_template_id"], ["bpo_task_templates.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bpo_tasks_assigned_user_id"), "bpo_tasks", ["assigned_user_id"], unique=False)
    op.create_index(op.f("ix_bpo_tasks_client_id"), "bpo_tasks", ["client_id"], unique=False)
    op.create_index(op.f("ix_bpo_tasks_competence_date"), "bpo_tasks", ["competence_date"], unique=False)
    op.create_index(op.f("ix_bpo_tasks_created_by_user_id"), "bpo_tasks", ["created_by_user_id"], unique=False)
    op.create_index(op.f("ix_bpo_tasks_due_date"), "bpo_tasks", ["due_date"], unique=False)
    op.create_index(op.f("ix_bpo_tasks_priority"), "bpo_tasks", ["priority"], unique=False)
    op.create_index(op.f("ix_bpo_tasks_status"), "bpo_tasks", ["status"], unique=False)
    op.create_index(op.f("ix_bpo_tasks_task_template_id"), "bpo_tasks", ["task_template_id"], unique=False)

    op.create_table(
        "bpo_task_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["bpo_tasks.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["d3_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bpo_task_events_task_id"), "bpo_task_events", ["task_id"], unique=False)
    op.create_index(op.f("ix_bpo_task_events_user_id"), "bpo_task_events", ["user_id"], unique=False)

    op.create_table(
        "bpo_conciliation_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("arquivo_vendas", sa.String(length=255), nullable=False),
        sa.Column("arquivo_recebimentos", sa.String(length=255), nullable=False),
        sa.Column("arquivo_saida", sa.String(length=255), nullable=False),
        sa.Column("total_vendas", sa.Integer(), nullable=False),
        sa.Column("total_recebimentos", sa.Integer(), nullable=False),
        sa.Column("total_divergencias", sa.Integer(), nullable=False),
        sa.Column("duracao_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["bpo_clients.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["bpo_tasks.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["d3_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bpo_conciliation_runs_client_id"), "bpo_conciliation_runs", ["client_id"], unique=False)
    op.create_index(op.f("ix_bpo_conciliation_runs_period_end"), "bpo_conciliation_runs", ["period_end"], unique=False)
    op.create_index(op.f("ix_bpo_conciliation_runs_period_start"), "bpo_conciliation_runs", ["period_start"], unique=False)
    op.create_index(op.f("ix_bpo_conciliation_runs_status"), "bpo_conciliation_runs", ["status"], unique=False)
    op.create_index(op.f("ix_bpo_conciliation_runs_task_id"), "bpo_conciliation_runs", ["task_id"], unique=False)
    op.create_index(op.f("ix_bpo_conciliation_runs_uploaded_by_user_id"), "bpo_conciliation_runs", ["uploaded_by_user_id"], unique=False)

    op.create_table(
        "bpo_conciliation_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conciliation_run_id", sa.Integer(), nullable=False),
        sa.Column("item_type", sa.String(length=40), nullable=False),
        sa.Column("reference_key", sa.String(length=255), nullable=False),
        sa.Column("sale_date", sa.Date(), nullable=True),
        sa.Column("expected_payment_date", sa.Date(), nullable=True),
        sa.Column("paid_date", sa.Date(), nullable=True),
        sa.Column("gross_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("net_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("difference_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["conciliation_run_id"], ["bpo_conciliation_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bpo_conciliation_items_conciliation_run_id"), "bpo_conciliation_items", ["conciliation_run_id"], unique=False)
    op.create_index(op.f("ix_bpo_conciliation_items_item_type"), "bpo_conciliation_items", ["item_type"], unique=False)
    op.create_index(op.f("ix_bpo_conciliation_items_reference_key"), "bpo_conciliation_items", ["reference_key"], unique=False)
    op.create_index(op.f("ix_bpo_conciliation_items_status"), "bpo_conciliation_items", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_bpo_conciliation_items_status"), table_name="bpo_conciliation_items")
    op.drop_index(op.f("ix_bpo_conciliation_items_reference_key"), table_name="bpo_conciliation_items")
    op.drop_index(op.f("ix_bpo_conciliation_items_item_type"), table_name="bpo_conciliation_items")
    op.drop_index(op.f("ix_bpo_conciliation_items_conciliation_run_id"), table_name="bpo_conciliation_items")
    op.drop_table("bpo_conciliation_items")

    op.drop_index(op.f("ix_bpo_conciliation_runs_uploaded_by_user_id"), table_name="bpo_conciliation_runs")
    op.drop_index(op.f("ix_bpo_conciliation_runs_task_id"), table_name="bpo_conciliation_runs")
    op.drop_index(op.f("ix_bpo_conciliation_runs_status"), table_name="bpo_conciliation_runs")
    op.drop_index(op.f("ix_bpo_conciliation_runs_period_start"), table_name="bpo_conciliation_runs")
    op.drop_index(op.f("ix_bpo_conciliation_runs_period_end"), table_name="bpo_conciliation_runs")
    op.drop_index(op.f("ix_bpo_conciliation_runs_client_id"), table_name="bpo_conciliation_runs")
    op.drop_table("bpo_conciliation_runs")

    op.drop_index(op.f("ix_bpo_task_events_user_id"), table_name="bpo_task_events")
    op.drop_index(op.f("ix_bpo_task_events_task_id"), table_name="bpo_task_events")
    op.drop_table("bpo_task_events")

    op.drop_index(op.f("ix_bpo_tasks_task_template_id"), table_name="bpo_tasks")
    op.drop_index(op.f("ix_bpo_tasks_status"), table_name="bpo_tasks")
    op.drop_index(op.f("ix_bpo_tasks_priority"), table_name="bpo_tasks")
    op.drop_index(op.f("ix_bpo_tasks_due_date"), table_name="bpo_tasks")
    op.drop_index(op.f("ix_bpo_tasks_created_by_user_id"), table_name="bpo_tasks")
    op.drop_index(op.f("ix_bpo_tasks_competence_date"), table_name="bpo_tasks")
    op.drop_index(op.f("ix_bpo_tasks_client_id"), table_name="bpo_tasks")
    op.drop_index(op.f("ix_bpo_tasks_assigned_user_id"), table_name="bpo_tasks")
    op.drop_table("bpo_tasks")

    op.drop_index(op.f("ix_bpo_recurring_routines_task_template_id"), table_name="bpo_recurring_routines")
    op.drop_index(op.f("ix_bpo_recurring_routines_default_assignee_user_id"), table_name="bpo_recurring_routines")
    op.drop_index(op.f("ix_bpo_recurring_routines_client_id"), table_name="bpo_recurring_routines")
    op.drop_table("bpo_recurring_routines")

    op.drop_index(op.f("ix_bpo_client_contacts_client_id"), table_name="bpo_client_contacts")
    op.drop_table("bpo_client_contacts")

    op.drop_index(op.f("ix_bpo_task_templates_service_type"), table_name="bpo_task_templates")
    op.drop_table("bpo_task_templates")

    op.drop_index(op.f("ix_bpo_clients_status"), table_name="bpo_clients")
    op.drop_index(op.f("ix_bpo_clients_responsible_user_id"), table_name="bpo_clients")
    op.drop_index(op.f("ix_bpo_clients_document"), table_name="bpo_clients")
    op.drop_table("bpo_clients")
