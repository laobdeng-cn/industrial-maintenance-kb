"""add improvement action change sets and verifications

Revision ID: c6e2a1f7d490
Revises: b9e5d2a4c801
Create Date: 2026-09-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c6e2a1f7d490"
down_revision: Union[str, None] = "b9e5d2a4c801"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "improvement_action_change_sets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("action_id", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("change_type", sa.String(length=40), nullable=False),
        sa.Column("target", sa.String(length=240), nullable=False),
        sa.Column("before_version", sa.String(length=160), nullable=True),
        sa.Column("after_version", sa.String(length=160), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("implemented_by", sa.String(length=120), nullable=True),
        sa.Column("implemented_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["action_id"],
            ["improvement_actions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "action_id",
            "sequence",
            name="uq_improvement_action_change_set_sequence",
        ),
    )
    op.create_index(
        "ix_improvement_action_change_sets_action_id",
        "improvement_action_change_sets",
        ["action_id"],
        unique=False,
    )
    op.create_index(
        "ix_improvement_action_change_sets_change_type",
        "improvement_action_change_sets",
        ["change_type"],
        unique=False,
    )
    op.create_index(
        "ix_improvement_action_change_sets_implemented_by",
        "improvement_action_change_sets",
        ["implemented_by"],
        unique=False,
    )

    op.create_table(
        "improvement_action_verifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("action_id", sa.Integer(), nullable=False),
        sa.Column("change_set_id", sa.Integer(), nullable=True),
        sa.Column("baseline_run_id", sa.Integer(), nullable=False),
        sa.Column("candidate_run_id", sa.Integer(), nullable=False),
        sa.Column("regression_status", sa.String(length=30), nullable=False),
        sa.Column("matched_case_count", sa.Integer(), nullable=False),
        sa.Column("metrics_snapshot", sa.JSON(), nullable=True),
        sa.Column("regression_summary", sa.JSON(), nullable=True),
        sa.Column(
            "automated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["action_id"],
            ["improvement_actions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["change_set_id"],
            ["improvement_action_change_sets.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["baseline_run_id"],
            ["evaluation_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_run_id"],
            ["evaluation_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "action_id",
            "candidate_run_id",
            name="uq_improvement_action_verification_candidate",
        ),
    )
    op.create_index(
        "ix_improvement_action_verifications_action_id",
        "improvement_action_verifications",
        ["action_id"],
        unique=False,
    )
    op.create_index(
        "ix_improvement_action_verifications_change_set_id",
        "improvement_action_verifications",
        ["change_set_id"],
        unique=False,
    )
    op.create_index(
        "ix_improvement_action_verifications_baseline_run_id",
        "improvement_action_verifications",
        ["baseline_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_improvement_action_verifications_candidate_run_id",
        "improvement_action_verifications",
        ["candidate_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_improvement_action_verifications_regression_status",
        "improvement_action_verifications",
        ["regression_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_improvement_action_verifications_regression_status",
        table_name="improvement_action_verifications",
    )
    op.drop_index(
        "ix_improvement_action_verifications_candidate_run_id",
        table_name="improvement_action_verifications",
    )
    op.drop_index(
        "ix_improvement_action_verifications_baseline_run_id",
        table_name="improvement_action_verifications",
    )
    op.drop_index(
        "ix_improvement_action_verifications_change_set_id",
        table_name="improvement_action_verifications",
    )
    op.drop_index(
        "ix_improvement_action_verifications_action_id",
        table_name="improvement_action_verifications",
    )
    op.drop_table("improvement_action_verifications")

    op.drop_index(
        "ix_improvement_action_change_sets_implemented_by",
        table_name="improvement_action_change_sets",
    )
    op.drop_index(
        "ix_improvement_action_change_sets_change_type",
        table_name="improvement_action_change_sets",
    )
    op.drop_index(
        "ix_improvement_action_change_sets_action_id",
        table_name="improvement_action_change_sets",
    )
    op.drop_table("improvement_action_change_sets")
