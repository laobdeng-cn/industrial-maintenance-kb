"""add citation ground truth and golden set hygiene support

Revision ID: e1a7c3d5f902
Revises: d8f4a2c7b901
Create Date: 2026-09-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1a7c3d5f902"
down_revision: Union[str, None] = "d8f4a2c7b901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "evaluation_cases",
        sa.Column(
            "allowed_citation_evidence_ids",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.add_column(
        "evaluation_results",
        sa.Column(
            "allowed_citation_evidence_ids",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )

    op.execute(
        """
        UPDATE evaluation_cases
        SET allowed_citation_evidence_ids = expected_evidence_ids
        """
    )
    op.execute(
        """
        UPDATE evaluation_results
        SET allowed_citation_evidence_ids = expected_evidence_ids
        """
    )

    op.alter_column(
        "evaluation_cases",
        "allowed_citation_evidence_ids",
        server_default=None,
    )
    op.alter_column(
        "evaluation_results",
        "allowed_citation_evidence_ids",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column(
        "evaluation_results",
        "allowed_citation_evidence_ids",
    )
    op.drop_column(
        "evaluation_cases",
        "allowed_citation_evidence_ids",
    )
