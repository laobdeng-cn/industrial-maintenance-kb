"""add review regression run links

Revision ID: a7c2e9d4b613
Revises: f4d1c8a92b73
Create Date: 2026-09-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7c2e9d4b613"
down_revision: Union[str, None] = "f4d1c8a92b73"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "review_queue",
        sa.Column("baseline_run_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "review_queue",
        sa.Column("last_regression_run_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_review_queue_baseline_run_id_evaluation_runs",
        "review_queue",
        "evaluation_runs",
        ["baseline_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_review_queue_last_regression_run_id_evaluation_runs",
        "review_queue",
        "evaluation_runs",
        ["last_regression_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_review_queue_baseline_run_id",
        "review_queue",
        ["baseline_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_review_queue_last_regression_run_id",
        "review_queue",
        ["last_regression_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_review_queue_last_regression_run_id", table_name="review_queue")
    op.drop_index("ix_review_queue_baseline_run_id", table_name="review_queue")
    op.drop_constraint(
        "fk_review_queue_last_regression_run_id_evaluation_runs",
        "review_queue",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_review_queue_baseline_run_id_evaluation_runs",
        "review_queue",
        type_="foreignkey",
    )
    op.drop_column("review_queue", "last_regression_run_id")
    op.drop_column("review_queue", "baseline_run_id")
