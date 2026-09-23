import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.deps import get_db
from app.models.document import DocumentVersion
from app.models.ingestion import IngestionJob
from app.schemas.document import (
    DocumentResponse,
    DocumentUploadResponse,
    IngestionJobResponse,
)
from app.services.storage import (
    InvalidPdfError,
    UploadTooLargeError,
    store_pdf,
)


router = APIRouter(
    prefix="/api/documents",
    tags=["documents"],
)

PARSER_CONFIG_VERSION = "parser-v1"
PARSER_CONFIG_HASH = hashlib.sha256(
    PARSER_CONFIG_VERSION.encode("utf-8")
).hexdigest()


def _latest_job(
    db: Session,
    document_version_id: int,
) -> IngestionJob | None:
    return db.scalar(
        select(IngestionJob)
        .where(IngestionJob.document_version_id == document_version_id)
        .order_by(IngestionJob.created_at.desc(), IngestionJob.id.desc())
        .limit(1)
    )


def _upload_response(
    document: DocumentVersion,
    job: IngestionJob | None,
    *,
    duplicate: bool,
) -> DocumentUploadResponse:
    return DocumentUploadResponse(
        duplicate=duplicate,
        document=DocumentResponse.model_validate(document),
        ingestion_job=(
            IngestionJobResponse.model_validate(job)
            if job is not None
            else None
        ),
    )


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    version: str | None = Form(default=None),
    language: str | None = Form(default=None),
    source_url: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> DocumentUploadResponse:
    try:
        stored = await store_pdf(
            upload=file,
            storage_root=settings.storage_root,
            max_upload_bytes=settings.max_upload_bytes,
        )
    except InvalidPdfError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except UploadTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        ) from exc

    existing = db.scalar(
        select(DocumentVersion).where(
            DocumentVersion.file_hash == stored.sha256
        )
    )
    if existing is not None:
        return _upload_response(
            existing,
            _latest_job(db, existing.id),
            duplicate=True,
        )

    normalized_title = (title or "").strip()
    if not normalized_title:
        normalized_title = Path(stored.original_filename).stem or "Untitled document"

    document = DocumentVersion(
        title=normalized_title,
        version=(version or "").strip() or None,
        language=(language or "").strip() or None,
        source_url=(source_url or "").strip() or None,
        original_filename=stored.original_filename,
        storage_path=stored.relative_path,
        file_hash=stored.sha256,
        status="draft",
    )

    idempotency_key = f"parse:{stored.sha256}:{PARSER_CONFIG_VERSION}"

    job = IngestionJob(
        document_version=document,
        job_type="parse",
        stage="queued",
        status="pending",
        input_hash=stored.sha256,
        idempotency_key=idempotency_key,
        parser_config_hash=PARSER_CONFIG_HASH,
    )

    db.add_all([document, job])

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(DocumentVersion).where(
                DocumentVersion.file_hash == stored.sha256
            )
        )
        if existing is None:
            raise

        return _upload_response(
            existing,
            _latest_job(db, existing.id),
            duplicate=True,
        )

    db.refresh(document)
    db.refresh(job)

    return _upload_response(
        document,
        job,
        duplicate=False,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
)
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
) -> DocumentResponse:
    document = db.get(DocumentVersion, document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="document not found",
        )

    return DocumentResponse.model_validate(document)
