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
