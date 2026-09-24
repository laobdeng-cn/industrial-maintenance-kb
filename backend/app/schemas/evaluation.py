from datetime import datetime
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


def _clean_evidence_ids(values: list[str] | None) -> list[str]:
    if not values:
        return []

    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        evidence_id = value.strip()
        if evidence_id and evidence_id not in seen:
            cleaned.append(evidence_id)
            seen.add(evidence_id)
    return cleaned


def _unique(values: list[int] | list[float]) -> list:
    return list(dict.fromkeys(values))


class EvaluationCaseCreate(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    equipment_model_id: int = Field(gt=0)
    expected_evidence_ids: list[str] = Field(default_factory=list)
    expected_answerable: bool = True
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("query")
    @classmethod
    def clean_query(cls, value: str) -> str:
        return value.strip()

    @field_validator("expected_evidence_ids")
    @classmethod
    def clean_evidence_ids(cls, value: list[str]) -> list[str]:
        return _clean_evidence_ids(value)


class EvaluationCaseUpdate(BaseModel):
    query: str | None = Field(default=None, min_length=2, max_length=2000)
    equipment_model_id: int | None = Field(default=None, gt=0)
    expected_evidence_ids: list[str] | None = None
    expected_answerable: bool | None = None
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("query")
    @classmethod
    def clean_query(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("expected_evidence_ids")
    @classmethod
    def clean_evidence_ids(cls, value: list[str] | None) -> list[str] | None:
        return _clean_evidence_ids(value) if value is not None else None


class EvaluationCaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    query: str
    equipment_model_id: int
    expected_evidence_ids: list[str]
    expected_answerable: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime


class EvaluationRunCreate(BaseModel):
    top_k: int = Field(default=5, ge=1, le=20)
    case_ids: list[int] | None = None
    rough_recall_limit: int | None = Field(default=None, ge=1, le=100)
    vector_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    rerank_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    grounding_min_final_score: float | None = Field(default=None, ge=0.0, le=1.0)
    grounding_min_rerank_score: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_tuning(self) -> Self:
        if self.rough_recall_limit is not None and self.rough_recall_limit < self.top_k:
            raise ValueError("rough_recall_limit must be >= top_k")

        one_weight_missing = (self.vector_weight is None) != (self.rerank_weight is None)
        if one_weight_missing:
            raise ValueError("vector_weight and rerank_weight must be provided together")
        if (
            self.vector_weight is not None
            and self.rerank_weight is not None
            and abs(self.vector_weight + self.rerank_weight - 1.0) > 1e-6
        ):
            raise ValueError("vector_weight + rerank_weight must equal 1.0")
        return self


class EvaluationSweepCreate(BaseModel):
    top_k_values: list[int] = Field(default_factory=lambda: [2, 3, 5, 8], min_length=1)
    grounding_min_final_score_values: list[float] = Field(
        default_factory=lambda: [0.30, 0.35, 0.40, 0.45],
        min_length=1,
    )
    grounding_min_rerank_score_values: list[float] = Field(
        default_factory=lambda: [0.10, 0.15, 0.20],
        min_length=1,
    )
    rough_recall_limit: int | None = Field(default=None, ge=1, le=100)
    vector_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    rerank_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    case_ids: list[int] | None = None

    @field_validator("top_k_values")
    @classmethod
    def validate_top_k_values(cls, value: list[int]) -> list[int]:
        cleaned = _unique(value)
        if any(item < 1 or item > 20 for item in cleaned):
            raise ValueError("top_k_values must be between 1 and 20")
        return cleaned

    @field_validator(
        "grounding_min_final_score_values",
        "grounding_min_rerank_score_values",
    )
    @classmethod
    def validate_threshold_values(cls, value: list[float]) -> list[float]:
        cleaned = _unique(value)
        if any(item < 0.0 or item > 1.0 for item in cleaned):
            raise ValueError("threshold values must be between 0 and 1")
        return cleaned

    @model_validator(mode="after")
    def validate_sweep(self) -> Self:
        if (
            self.rough_recall_limit is not None
            and self.rough_recall_limit < max(self.top_k_values)
        ):
            raise ValueError("rough_recall_limit must be >= max(top_k_values)")

        one_weight_missing = (self.vector_weight is None) != (self.rerank_weight is None)
        if one_weight_missing:
            raise ValueError("vector_weight and rerank_weight must be provided together")
        if (
            self.vector_weight is not None
            and self.rerank_weight is not None
            and abs(self.vector_weight + self.rerank_weight - 1.0) > 1e-6
        ):
            raise ValueError("vector_weight + rerank_weight must equal 1.0")

        combinations = (
            len(self.top_k_values)
            * len(self.grounding_min_final_score_values)
            * len(self.grounding_min_rerank_score_values)
        )
        if combinations > 64:
            raise ValueError("a single sweep is limited to 64 parameter combinations")
        return self


class EvaluationResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    case_id: int | None
    query: str
    equipment_model_id: int
    expected_evidence_ids: list[str]
    expected_answerable: bool
    grounded: bool
    refusal_reason: str | None
    answer: str
    hits: list[dict]
    citation_evidence_ids: list[str]
    hit_at_k: bool | None
    first_relevant_rank: int | None
    reciprocal_rank: float | None
    citation_precision: float | None
    citation_recall: float | None
    answerability_correct: bool
    latency_ms: int
    error_message: str | None
    decision_trace: dict | None
    created_at: datetime


class EvaluationRunSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    top_k: int
    total_cases: int
    completed_cases: int
    metrics: dict | None
    parameter_snapshot: dict | None
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime


class EvaluationRunResponse(EvaluationRunSummaryResponse):
    results: list[EvaluationResultResponse]


class EvaluationSweepResponse(BaseModel):
    combination_count: int
    case_count: int
    estimated_case_executions: int
    runs: list[EvaluationRunSummaryResponse]


class EvaluationLeaderboardItem(BaseModel):
    run_id: int
    status: str
    total_cases: int
    parameter_snapshot: dict | None
    hit_at_k: float | None
    mrr: float | None
    refusal_accuracy: float | None
    answerability_accuracy: float | None
    citation_f1: float | None
    avg_latency_ms: float | None
    failure_count: int
    issue_counts: dict[str, int]
    created_at: datetime


class ThresholdEvidenceResponse(BaseModel):
    rank: int
    evidence_id: str
    section_path: str | None
    text: str
    vector_score: float
    rerank_score: float
    final_score: float


class ThresholdErrorAnalysisResponse(BaseModel):
    result_id: int
    case_id: int | None
    query: str
    expected_answerable: bool
    actual_grounded: bool
    refusal_reason: str | None
    top_final_score: float | None
    top_rerank_score: float | None
    grounding_min_final_score: float | None
    grounding_min_rerank_score: float | None
    final_margin: float | None
    rerank_margin: float | None
    decision_source: str | None
    deepseek_answerable: bool | None
    deepseek_reason: str | None
    top_evidence: list[ThresholdEvidenceResponse]


class EvaluationComparisonResultSnapshot(BaseModel):
    grounded: bool
    answerability_correct: bool
    hit_at_k: bool | None
    first_relevant_rank: int | None
    reciprocal_rank: float | None
    citation_precision: float | None
    citation_recall: float | None
    latency_ms: int
    error_message: str | None


class EvaluationComparisonSample(BaseModel):
    case_id: int | None
    query: str
    status: str
    comparable: bool
    baseline_issue_codes: list[str]
    candidate_issue_codes: list[str]
    regression_reasons: list[str]
    improvement_reasons: list[str]
    baseline: EvaluationComparisonResultSnapshot
    candidate: EvaluationComparisonResultSnapshot


class EvaluationRunComparisonResponse(BaseModel):
    baseline_run: EvaluationRunSummaryResponse
    candidate_run: EvaluationRunSummaryResponse
    metric_deltas: dict[str, dict[str, float | None]]
    failure_deltas: dict[str, dict[str, int]]
    matched_case_count: int
    baseline_only_case_count: int
    candidate_only_case_count: int
    regressed_count: int
    improved_count: int
    mixed_count: int
    unchanged_count: int
    incomparable_count: int
    samples: list[EvaluationComparisonSample]
