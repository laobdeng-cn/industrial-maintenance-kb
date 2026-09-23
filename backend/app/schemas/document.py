from datetime import datetime

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
    created_at: datetime


class DocumentUploadResponse(BaseModel):
    duplicate: bool
    document: DocumentResponse
    ingestion_job: IngestionJobResponse | None
