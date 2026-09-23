"""add index generations

Revision ID: c3b7a1d942ef
Revises: 7500a06a1b83
Create Date: 2026-09-24 05:45:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3b7a1d942ef"
down_revision: Union[str, Sequence[str], None] = "7500a06a1b83"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "index_generations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_version_id", sa.Integer(), nullable=False),
        sa.Column("embedding_model", sa.String(length=255), nullable=False),
        sa.Column("collection_name", sa.String(length=120), nullable=False),
        sa.Column("vector_size", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "point_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
            ["document_version_id"],
            ["document_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_version_id",
            "embedding_model",
            name="uq_index_generation_document_model",
        ),
    )
    op.create_index(
        op.f("ix_index_generations_document_version_id"),
        "index_generations",
        ["document_version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_index_generations_status"),
        "index_generations",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_index_generations_status"),
        table_name="index_generations",
    )
    op.drop_index(
        op.f("ix_index_generations_document_version_id"),
        table_name="index_generations",
    )
    op.drop_table("index_generations")
