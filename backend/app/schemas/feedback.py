from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AnswerFeedbackCreate(BaseModel):
    rating: Literal["helpful", "unhelpful"]
    reason: str | None = Field(default=None, max_length=120)
    comment: str | None = Field(default=None, max_length=4000)

    @field_validator("reason", "comment")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class AnswerFeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    query_log_id: int
    rating: str
    reason: str | None
    comment: str | None
    created_at: datetime
    updated_at: datetime


class ReviewQueueUpdate(BaseModel):
    status: Literal["pending", "accepted", "ignored"]
    reviewer_note: str | None = Field(default=None, max_length=4000)

    @field_validator("reviewer_note")
    @classmethod
    def clean_reviewer_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ReviewQueueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    query_log_id: int
    status: str
    reviewer_note: str | None
    promoted_case_id: int | None
    created_at: datetime
    updated_at: datetime


class QueryLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    query: str
    equipment_model_id: int
    grounded: bool
    answer: str
    refusal_reason: str | None
    decision_source: str
    top_final_score: float | None
    top_rerank_score: float | None
    citations: list[dict]
    hits: list[dict]
    latency_ms: int
    created_at: datetime
    feedback: AnswerFeedbackResponse | None = None
    review_item: ReviewQueueResponse | None = None


class AnalyticsBucket(BaseModel):
    key: str
    label: str
    count: int
    percentage: float


class FeedbackTrendPoint(BaseModel):
    date: str
    total_queries: int
    helpful: int
    unhelpful: int
    review_created: int


class ReviewSLAItem(BaseModel):
    review_id: int
    query_log_id: int
    query: str
    equipment_model_id: int
    status: str
    created_at: datetime
    due_at: datetime
    age_hours: float
    sla_hours: float
    sla_state: Literal["on_track", "due_soon", "overdue", "resolved"]
    feedback_rating: str | None = None
    feedback_reason: str | None = None


class FeedbackAnalyticsResponse(BaseModel):
    window_days: int
    sla_hours: float
    total_queries: int
    grounded_count: int
    refused_count: int
    feedback_total: int
    helpful_count: int
    unhelpful_count: int
    helpful_rate: float | None
    avg_latency_ms: float | None
    review_total: int
    review_pending: int
    review_overdue: int
    review_due_soon: int
    review_resolved: int
    review_sla_met: int
    review_sla_breached: int
    review_sla_compliance_rate: float | None
    oldest_pending_hours: float | None
    decision_sources: list[AnalyticsBucket]
    equipment_models: list[AnalyticsBucket]
    trend: list[FeedbackTrendPoint]
    review_sla_items: list[ReviewSLAItem]


class QueryClusterMember(BaseModel):
    query_log_id: int
    query: str
    equipment_model_id: int
    grounded: bool
    feedback_rating: str | None
    review_status: str | None
    created_at: datetime


class QueryCluster(BaseModel):
    cluster_id: int
    representative_query: str
    size: int
    unhelpful_count: int
    pending_review_count: int
    grounded_count: int
    equipment_model_ids: list[int]
    members: list[QueryClusterMember]


class QueryClusterResponse(BaseModel):
    window_days: int
    similarity_threshold: float
    only_problematic: bool
    sample_count: int
    cluster_count: int
    clusters: list[QueryCluster]
