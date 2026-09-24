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
    baseline_run_id: int | None
    last_regression_run_id: int | None
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
    review_id: int | None
    review_status: str | None
    promoted_case_id: int | None
    baseline_run_id: int | None
    last_regression_run_id: int | None
    top_final_score: float | None
    top_rerank_score: float | None
    decision_source: str
    citation_count: int
    hit_count: int
    latency_ms: int
    created_at: datetime


class QueryCluster(BaseModel):
    cluster_id: int
    cluster_key: str
    representative_query: str
    size: int
    unhelpful_count: int
    pending_review_count: int
    overdue_review_count: int
    grounded_count: int
    priority_score: float
    priority_level: Literal["urgent", "high", "medium", "low"]
    priority_reasons: list[str]
    equipment_model_ids: list[int]
    promoted_case_ids: list[int]
    baseline_run_ids: list[int]
    last_regression_run_ids: list[int]
    members: list[QueryClusterMember]


class QueryClusterDrilldownRequest(BaseModel):
    query_log_ids: list[int] = Field(min_length=1, max_length=100)

    @field_validator("query_log_ids")
    @classmethod
    def unique_query_log_ids(cls, value: list[int]) -> list[int]:
        return list(dict.fromkeys(value))


class ClusterBatchReviewCreate(BaseModel):
    query_log_ids: list[int] = Field(min_length=1, max_length=100)
    action: Literal["promote", "ignore", "pending"]
    reviewer_note: str | None = Field(default=None, max_length=4000)
    create_baseline: bool = True
    top_k: int = Field(default=5, ge=1, le=20)

    @field_validator("query_log_ids")
    @classmethod
    def unique_batch_query_log_ids(cls, value: list[int]) -> list[int]:
        return list(dict.fromkeys(value))

    @field_validator("reviewer_note")
    @classmethod
    def clean_batch_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ClusterBatchReviewResponse(BaseModel):
    action: str
    processed_count: int
    created_review_count: int
    promoted_case_ids: list[int]
    baseline_run_id: int | None
    reviews: list[ReviewQueueResponse]


class ClusterRegressionCreate(BaseModel):
    query_log_ids: list[int] = Field(min_length=1, max_length=100)
    baseline_run_id: int | None = Field(default=None, gt=0)
    top_k: int = Field(default=5, ge=1, le=20)
    rough_recall_limit: int | None = Field(default=None, ge=1, le=100)
    vector_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    rerank_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    grounding_min_final_score: float | None = Field(default=None, ge=0.0, le=1.0)
    grounding_min_rerank_score: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("query_log_ids")
    @classmethod
    def unique_regression_query_log_ids(cls, value: list[int]) -> list[int]:
        return list(dict.fromkeys(value))


class ClusterRegressionResponse(BaseModel):
    baseline_run_id: int
    candidate_run_id: int
    case_ids: list[int]
    candidate_metrics: dict | None
    comparison_path: str


class QueryClusterResponse(BaseModel):
    window_days: int
    similarity_threshold: float
    only_problematic: bool
    sample_count: int
    cluster_count: int
    clusters: list[QueryCluster]
