"""add evaluation center tables

Revision ID: 7d4e8c1f2a90
Revises: c3b7a1d942ef
Create Date: 2026-09-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7d4e8c1f2a90"
down_revision: Union[str, None] = "c3b7a1d942ef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "evaluation_cases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("equipment_model_id", sa.Integer(), nullable=False),
        sa.Column("expected_evidence_ids", sa.JSON(), nullable=False),
        sa.Column("expected_answerable", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["equipment_model_id"],
            ["equipment_models.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evaluation_cases_equipment_model_id",
        "evaluation_cases",
        ["equipment_model_id"],
        unique=False,
    )

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("total_cases", sa.Integer(), nullable=False),
        sa.Column("completed_cases", sa.Integer(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evaluation_runs_status",
        "evaluation_runs",
        ["status"],
        unique=False,
    )

    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("case_id", sa.Integer(), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("equipment_model_id", sa.Integer(), nullable=False),
        sa.Column("expected_evidence_ids", sa.JSON(), nullable=False),
        sa.Column("expected_answerable", sa.Boolean(), nullable=False),
        sa.Column("grounded", sa.Boolean(), nullable=False),
        sa.Column("refusal_reason", sa.String(length=120), nullable=True),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("hits", sa.JSON(), nullable=False),
        sa.Column("citation_evidence_ids", sa.JSON(), nullable=False),
        sa.Column("hit_at_k", sa.Boolean(), nullable=True),
        sa.Column("first_relevant_rank", sa.Integer(), nullable=True),
        sa.Column("reciprocal_rank", sa.Float(), nullable=True),
        sa.Column("citation_precision", sa.Float(), nullable=True),
        sa.Column("citation_recall", sa.Float(), nullable=True),
        sa.Column("answerability_correct", sa.Boolean(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["evaluation_cases.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["evaluation_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evaluation_results_case_id",
        "evaluation_results",
        ["case_id"],
        unique=False,
    )
    op.create_index(
        "ix_evaluation_results_run_id",
        "evaluation_results",
        ["run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_evaluation_results_run_id",
        table_name="evaluation_results",
    )
    op.drop_index(
        "ix_evaluation_results_case_id",
        table_name="evaluation_results",
    )
    op.drop_table("evaluation_results")

    op.drop_index(
        "ix_evaluation_runs_status",
        table_name="evaluation_runs",
    )
    op.drop_table("evaluation_runs")

    op.drop_index(
        "ix_evaluation_cases_equipment_model_id",
        table_name="evaluation_cases",
    )
    op.drop_table("evaluation_cases")
