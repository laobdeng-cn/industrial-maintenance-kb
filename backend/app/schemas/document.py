from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    version: str | None
    language: str | None
    source_url: str | None
    original_filename: str | None
    file_hash: str
    status: str
    created_at: datetime
    published_at: datetime | None


class DocumentBlockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    evidence_id: str
    document_version_id: int
    block_type: str
    section_path: str | None
    page_start: int | None
    page_end: int | None
    bbox: dict[str, Any] | None
    text: str | None
    asset_id: int | None
    ordinal: int
    extra_metadata: dict[str, Any] | None


class DocumentAssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_version_id: int
    asset_type: str
    page_number: int | None
    mime_type: str | None
    sha256: str | None
    bbox: dict[str, Any] | None
    caption: str | None
    storage_path: str
    created_at: datetime


class IngestionJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_version_id: int | None
    job_type: str
    stage: str
    status: str
    input_hash: str
    idempotency_key: str
    retry_count: int
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class DocumentUploadResponse(BaseModel):
    duplicate: bool
    document: DocumentResponse
    ingestion_job: IngestionJobResponse | None
