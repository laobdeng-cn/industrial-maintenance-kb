from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class QueryLog(Base):
    __tablename__ = "query_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    equipment_model_id: Mapped[int] = mapped_column(
        ForeignKey("equipment_models.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    grounded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    refusal_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    decision_source: Mapped[str] = mapped_column(String(80), nullable=False)
    top_final_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    top_rerank_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    citations: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    hits: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    equipment_model = relationship("EquipmentModel")
    feedback = relationship(
        "AnswerFeedback",
        back_populates="query_log",
        uselist=False,
        cascade="all, delete-orphan",
    )
    review_item = relationship(
        "ReviewQueueItem",
        back_populates="query_log",
        uselist=False,
        cascade="all, delete-orphan",
    )


class AnswerFeedback(Base):
    __tablename__ = "answer_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_log_id: Mapped[int] = mapped_column(
        ForeignKey("query_logs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    rating: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    query_log = relationship("QueryLog", back_populates="feedback")


class ReviewQueueItem(Base):
    __tablename__ = "review_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_log_id: Mapped[int] = mapped_column(
        ForeignKey("query_logs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    promoted_case_id: Mapped[int | None] = mapped_column(
        ForeignKey("evaluation_cases.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    query_log = relationship("QueryLog", back_populates="review_item")
