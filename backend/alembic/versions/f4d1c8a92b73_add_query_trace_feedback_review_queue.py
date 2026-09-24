"""add query trace feedback and review queue

Revision ID: f4d1c8a92b73
Revises: e1a7c3d5f902
Create Date: 2026-09-24
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "f4d1c8a92b73"
down_revision: Union[str, None] = "e1a7c3d5f902"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "query_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("equipment_model_id", sa.Integer(), nullable=False),
        sa.Column("grounded", sa.Boolean(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("refusal_reason", sa.String(length=120), nullable=True),
        sa.Column("decision_source", sa.String(length=80), nullable=False),
        sa.Column("top_final_score", sa.Float(), nullable=True),
        sa.Column("top_rerank_score", sa.Float(), nullable=True),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("hits", sa.JSON(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["equipment_model_id"], ["equipment_models.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_query_logs_equipment_model_id", "query_logs", ["equipment_model_id"], unique=False)
    op.create_index("ix_query_logs_created_at", "query_logs", ["created_at"], unique=False)

    op.create_table(
        "answer_feedback",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("query_log_id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.String(length=120), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["query_log_id"], ["query_logs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("query_log_id"),
    )
    op.create_index("ix_answer_feedback_query_log_id", "answer_feedback", ["query_log_id"], unique=True)
    op.create_index("ix_answer_feedback_rating", "answer_feedback", ["rating"], unique=False)

    op.create_table(
        "review_queue",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("query_log_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column("promoted_case_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["promoted_case_id"], ["evaluation_cases.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["query_log_id"], ["query_logs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("query_log_id"),
    )
    op.create_index("ix_review_queue_query_log_id", "review_queue", ["query_log_id"], unique=True)
    op.create_index("ix_review_queue_status", "review_queue", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_review_queue_status", table_name="review_queue")
    op.drop_index("ix_review_queue_query_log_id", table_name="review_queue")
    op.drop_table("review_queue")
    op.drop_index("ix_answer_feedback_rating", table_name="answer_feedback")
    op.drop_index("ix_answer_feedback_query_log_id", table_name="answer_feedback")
    op.drop_table("answer_feedback")
    op.drop_index("ix_query_logs_created_at", table_name="query_logs")
    op.drop_index("ix_query_logs_equipment_model_id", table_name="query_logs")
    op.drop_table("query_logs")
