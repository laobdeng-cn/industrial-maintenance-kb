from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class IndexGenerationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_version_id: int
    embedding_model: str
    collection_name: str
    vector_size: int
    status: str
    point_count: int
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    equipment_model_id: int = Field(gt=0)
    limit: int = Field(default=5, ge=1, le=20)
    score_threshold: float | None = Field(default=None, ge=-1.0, le=1.0)


class SearchHitResponse(BaseModel):
    score: float
    vector_score: float
    rerank_score: float
    final_score: float
    point_id: int | str
    document_id: int
    block_id: int
    evidence_id: str
    title: str
    version: str | None
    language: str | None
    block_type: str
    section_path: str | None
    page_start: int | None
    page_end: int | None
    asset_id: int | None
    text: str


class SearchResponse(BaseModel):
    query: str
    equipment_model_id: int
    embedding_model: str
    collection_name: str
    rough_recall_limit: int
    hits: list[SearchHitResponse]


class GroundedCitationResponse(BaseModel):
    index: int
    evidence_id: str
    document_id: int
    block_id: int
    title: str
    version: str | None
    section_path: str | None
    page_start: int | None
    page_end: int | None
    asset_id: int | None
    text: str


class GroundedAnswerResponse(BaseModel):
    query: str
    equipment_model_id: int
    grounded: bool
    answer: str
    refusal_reason: str | None
    model: str | None
    grounding_threshold: float
    grounding_rerank_threshold: float
    top_final_score: float | None
    top_rerank_score: float | None
    decision_source: str
    deepseek_answerable: bool | None
    deepseek_reason: str | None
    embedding_model: str
    collection_name: str
    rough_recall_limit: int
    citations: list[GroundedCitationResponse]
    hits: list[SearchHitResponse]
