"""add evaluation decision traces

Revision ID: d8f4a2c7b901
Revises: 9c1e4b7a2f10
Create Date: 2026-09-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d8f4a2c7b901"
down_revision: Union[str, None] = "9c1e4b7a2f10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "evaluation_results",
        sa.Column("decision_trace", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("evaluation_results", "decision_trace")
