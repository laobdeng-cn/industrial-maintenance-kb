"""add improvement action tracking

Revision ID: b9e5d2a4c801
Revises: a7c2e9d4b613
Create Date: 2026-09-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b9e5d2a4c801"
down_revision: Union[str, None] = "a7c2e9d4b613"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "improvement_actions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cluster_key", sa.String(length=160), nullable=False),
        sa.Column("root_cause", sa.String(length=80), nullable=False),
        sa.Column("diagnosis_status", sa.String(length=40), nullable=False),
        sa.Column("action_type", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_query", sa.Text(), nullable=False),
        sa.Column("source_query_log_ids", sa.JSON(), nullable=False),
        sa.Column("source_recommendation_index", sa.Integer(), nullable=True),
        sa.Column("owner", sa.String(length=120), nullable=True),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("baseline_run_id", sa.Integer(), nullable=True),
        sa.Column("candidate_run_id", sa.Integer(), nullable=True),
        sa.Column("regression_status", sa.String(length=30), nullable=True),
        sa.Column("regression_summary", sa.JSON(), nullable=True),
        sa.Column("close_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["baseline_run_id"], ["evaluation_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["candidate_run_id"], ["evaluation_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_improvement_actions_cluster_key", "improvement_actions", ["cluster_key"], unique=False)
    op.create_index("ix_improvement_actions_root_cause", "improvement_actions", ["root_cause"], unique=False)
    op.create_index("ix_improvement_actions_owner", "improvement_actions", ["owner"], unique=False)
    op.create_index("ix_improvement_actions_priority", "improvement_actions", ["priority"], unique=False)
    op.create_index("ix_improvement_actions_status", "improvement_actions", ["status"], unique=False)
    op.create_index("ix_improvement_actions_due_at", "improvement_actions", ["due_at"], unique=False)
    op.create_index("ix_improvement_actions_baseline_run_id", "improvement_actions", ["baseline_run_id"], unique=False)
    op.create_index("ix_improvement_actions_candidate_run_id", "improvement_actions", ["candidate_run_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_improvement_actions_candidate_run_id", table_name="improvement_actions")
    op.drop_index("ix_improvement_actions_baseline_run_id", table_name="improvement_actions")
    op.drop_index("ix_improvement_actions_due_at", table_name="improvement_actions")
    op.drop_index("ix_improvement_actions_status", table_name="improvement_actions")
    op.drop_index("ix_improvement_actions_priority", table_name="improvement_actions")
    op.drop_index("ix_improvement_actions_owner", table_name="improvement_actions")
    op.drop_index("ix_improvement_actions_root_cause", table_name="improvement_actions")
    op.drop_index("ix_improvement_actions_cluster_key", table_name="improvement_actions")
    op.drop_table("improvement_actions")
