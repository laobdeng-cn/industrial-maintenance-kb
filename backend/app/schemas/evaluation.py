from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    def clean_evidence_ids(
        cls,
        value: list[str] | None,
    ) -> list[str] | None:
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
    created_at: datetime


class EvaluationRunSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    top_k: int
    total_cases: int
    completed_cases: int
    metrics: dict | None
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime


class EvaluationRunResponse(EvaluationRunSummaryResponse):
    results: list[EvaluationResultResponse]
