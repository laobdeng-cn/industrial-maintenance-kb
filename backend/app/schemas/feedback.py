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


class ImprovementRecommendation(BaseModel):
    action: str
    title: str
    detail: str


class ClusterDiagnosis(BaseModel):
    cluster_id: int
    cluster_key: str
    representative_query: str
    root_cause: Literal[
        "knowledge_gap",
        "retrieval_gap",
        "ranking_problem",
        "answerability_gate",
        "citation_problem",
        "prompt_generation",
    ]
    confidence: float
    diagnosis_status: Literal[
        "needs_human_validation",
        "probable",
        "confirmed",
        "resolved_by_regression",
    ]
    knowledge_gap_score: float
    coverage_status: Literal["covered", "partial", "missing", "unknown"]
    summary: str
    signals: list[str]
    recommendations: list[ImprovementRecommendation]
    affected_query_log_ids: list[int]
    promoted_case_ids: list[int]
    expected_evidence_count: int
    expected_hit_coverage: float | None
    average_top_final_score: float | None
    average_top_rerank_score: float | None
    review_signal_counts: dict[str, int]
    regression_signal_counts: dict[str, int]
    priority_score: float
    priority_level: Literal["urgent", "high", "medium", "low"]


class ClusterDiagnosisResponse(BaseModel):
    window_days: int
    similarity_threshold: float
    only_problematic: bool
    sample_count: int
    cluster_count: int
    clusters: list[QueryCluster]
    knowledge_gap_count: int
    root_cause_counts: dict[str, int]
    diagnosis_status_counts: dict[str, int]
    root_cause_status_counts: dict[str, dict[str, int]]
    confirmed_issue_count: int
    probable_issue_count: int
    needs_validation_count: int
    resolved_issue_count: int
    coverage_counts: dict[str, int]
    diagnostics: list[ClusterDiagnosis]


class QueryClusterResponse(BaseModel):
    window_days: int
    similarity_threshold: float
    only_problematic: bool
    sample_count: int
    cluster_count: int
    clusters: list[QueryCluster]



class ImprovementActionCreate(BaseModel):
    cluster_key: str = Field(min_length=1, max_length=160)
    root_cause: Literal[
        "knowledge_gap",
        "retrieval_gap",
        "ranking_problem",
        "answerability_gate",
        "citation_problem",
        "prompt_generation",
    ]
    diagnosis_status: Literal[
        "needs_human_validation",
        "probable",
        "confirmed",
        "resolved_by_regression",
    ]
    action_type: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=8000)
    source_query: str = Field(min_length=1, max_length=8000)
    source_query_log_ids: list[int] = Field(default_factory=list)
    source_recommendation_index: int | None = Field(default=None, ge=0)
    owner: str | None = Field(default=None, max_length=120)
    priority: Literal["urgent", "high", "medium", "low"] = "medium"
    due_at: datetime | None = None
    baseline_run_id: int | None = Field(default=None, ge=1)
    candidate_run_id: int | None = Field(default=None, ge=1)

    @field_validator("cluster_key", "action_type", "title", "source_query")
    @classmethod
    def clean_required_improvement_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value must not be blank")
        return cleaned

    @field_validator("description", "owner")
    @classmethod
    def clean_optional_improvement_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("source_query_log_ids")
    @classmethod
    def unique_source_query_log_ids(cls, value: list[int]) -> list[int]:
        return list(dict.fromkeys(value))


class ImprovementActionUpdate(BaseModel):
    owner: str | None = Field(default=None, max_length=120)
    priority: Literal["urgent", "high", "medium", "low"] | None = None
    status: Literal["open", "in_progress", "blocked", "done", "closed"] | None = None
    due_at: datetime | None = None
    description: str | None = Field(default=None, max_length=8000)
    baseline_run_id: int | None = Field(default=None, ge=1)
    candidate_run_id: int | None = Field(default=None, ge=1)
    close_note: str | None = Field(default=None, max_length=8000)

    @field_validator("owner", "description", "close_note")
    @classmethod
    def clean_improvement_update_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ImprovementRegressionLink(BaseModel):
    baseline_run_id: int = Field(ge=1)
    candidate_run_id: int = Field(ge=1)
    close_on_no_regression: bool = False


class ImprovementActionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cluster_key: str
    root_cause: str
    diagnosis_status: str
    action_type: str
    title: str
    description: str | None
    source_query: str
    source_query_log_ids: list[int]
    source_recommendation_index: int | None
    owner: str | None
    priority: str
    status: str
    due_at: datetime | None
    baseline_run_id: int | None
    candidate_run_id: int | None
    regression_status: str | None
    regression_summary: dict | None
    close_note: str | None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None


class ImprovementActionSummary(BaseModel):
    total: int
    open: int
    in_progress: int
    blocked: int
    done: int
    closed: int
    overdue: int
    with_regression: int


class ImprovementActionListResponse(BaseModel):
    summary: ImprovementActionSummary
    actions: list[ImprovementActionResponse]



class ActionROIComponents(BaseModel):
    outcome_points: float
    stability_points: float
    recurrence_penalty: float
    overdue_penalty: float
    cycle_cost_factor: float
    raw_impact: float
    roi_index: float
    formula: str


class ActionRecurrenceEvent(BaseModel):
    query_log_id: int
    query: str
    created_at: datetime
    similarity: float
    feedback_rating: str | None
    review_status: str | None


class ActionEffectivenessItem(BaseModel):
    action_id: int
    title: str
    root_cause: str
    owner: str | None
    priority: str
    status: str
    created_at: datetime
    closed_at: datetime | None
    cycle_hours: float | None
    baseline_run_id: int | None
    candidate_run_id: int | None
    regression_status: str | None
    recurrence_count: int
    first_recurrence_at: datetime | None
    last_recurrence_at: datetime | None
    recurrence_events: list[ActionRecurrenceEvent]
    roi: ActionROIComponents


class EffectivenessBreakdownItem(BaseModel):
    key: str
    label: str
    action_count: int
    verified_count: int
    improved_count: int
    unchanged_count: int
    regressed_count: int
    mixed_count: int
    recurrence_action_count: int
    improvement_rate: float | None
    non_regression_rate: float | None
    recurrence_rate: float | None
    avg_roi_index: float | None


class ImprovementEffectivenessSummary(BaseModel):
    action_count: int
    completed_action_count: int
    verified_action_count: int
    improved_count: int
    unchanged_count: int
    regressed_count: int
    mixed_count: int
    incomparable_count: int
    unverified_count: int
    overdue_count: int
    improvement_rate: float | None
    non_regression_rate: float | None
    regression_rate: float | None
    avg_cycle_hours: float | None
    recurrence_action_count: int
    recurrence_event_count: int
    recurrence_rate: float | None
    avg_roi_index: float | None


class ImprovementEffectivenessResponse(BaseModel):
    window_days: int
    recurrence_similarity_threshold: float
    recurrence_definition: str
    roi_definition: str
    summary: ImprovementEffectivenessSummary
    by_root_cause: list[EffectivenessBreakdownItem]
    by_priority: list[EffectivenessBreakdownItem]
    by_owner: list[EffectivenessBreakdownItem]
    actions: list[ActionEffectivenessItem]
