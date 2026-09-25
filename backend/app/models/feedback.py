from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
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
    baseline_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    last_regression_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    query_log = relationship("QueryLog", back_populates="review_item")



class ImprovementAction(Base):
    __tablename__ = "improvement_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cluster_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    root_cause: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    diagnosis_status: Mapped[str] = mapped_column(String(40), nullable=False)
    action_type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_query: Mapped[str] = mapped_column(Text, nullable=False)
    source_query_log_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    source_recommendation_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    owner: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="medium", index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open", index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    baseline_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    candidate_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    regression_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    regression_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    close_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    baseline_run = relationship("EvaluationRun", foreign_keys=[baseline_run_id])
    candidate_run = relationship("EvaluationRun", foreign_keys=[candidate_run_id])
    change_sets = relationship(
        "ImprovementActionChangeSet",
        back_populates="action",
        cascade="all, delete-orphan",
        order_by="ImprovementActionChangeSet.sequence",
    )
    verifications = relationship(
        "ImprovementActionVerification",
        back_populates="action",
        cascade="all, delete-orphan",
        order_by="ImprovementActionVerification.id",
    )


class ImprovementActionChangeSet(Base):
    __tablename__ = "improvement_action_change_sets"
    __table_args__ = (
        UniqueConstraint(
            "action_id",
            "sequence",
            name="uq_improvement_action_change_set_sequence",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action_id: Mapped[int] = mapped_column(
        ForeignKey("improvement_actions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    change_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    target: Mapped[str] = mapped_column(String(240), nullable=False)
    before_version: Mapped[str | None] = mapped_column(String(160), nullable=True)
    after_version: Mapped[str | None] = mapped_column(String(160), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    implemented_by: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    implemented_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    action = relationship("ImprovementAction", back_populates="change_sets")
    verifications = relationship(
        "ImprovementActionVerification",
        back_populates="change_set",
        order_by="ImprovementActionVerification.id",
    )


class ImprovementActionVerification(Base):
    __tablename__ = "improvement_action_verifications"
    __table_args__ = (
        UniqueConstraint(
            "action_id",
            "candidate_run_id",
            name="uq_improvement_action_verification_candidate",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action_id: Mapped[int] = mapped_column(
        ForeignKey("improvement_actions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    change_set_id: Mapped[int | None] = mapped_column(
        ForeignKey("improvement_action_change_sets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    baseline_run_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    candidate_run_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    regression_status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    matched_case_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metrics_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    regression_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    automated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    action = relationship("ImprovementAction", back_populates="verifications")
    change_set = relationship("ImprovementActionChangeSet", back_populates="verifications")
    baseline_run = relationship("EvaluationRun", foreign_keys=[baseline_run_id])
    candidate_run = relationship("EvaluationRun", foreign_keys=[candidate_run_id])
