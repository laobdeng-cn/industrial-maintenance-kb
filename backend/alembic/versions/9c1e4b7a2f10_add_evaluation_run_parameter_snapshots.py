"""add evaluation run parameter snapshots

Revision ID: 9c1e4b7a2f10
Revises: 7d4e8c1f2a90
Create Date: 2026-09-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9c1e4b7a2f10"
down_revision: Union[str, None] = "7d4e8c1f2a90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "evaluation_runs",
        sa.Column("parameter_snapshot", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("evaluation_runs", "parameter_snapshot")
