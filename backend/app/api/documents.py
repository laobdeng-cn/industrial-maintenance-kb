from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.parser import PARSER_CONFIG_HASH, PARSER_CONFIG_VERSION
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
from app.workers.celery_app import celery_app


router = APIRouter(
    prefix="/api/documents",
    tags=["documents"],
)

PARSE_TASK_NAME = "app.workers.tasks.parse_document"


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


def _enqueue_job(job_id: int) -> None:
    celery_app.send_task(
        PARSE_TASK_NAME,
        args=[job_id],
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

    idempotency_key = (
        f"parse:{stored.sha256}:{PARSER_CONFIG_VERSION}"
    )

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

    try:
        _enqueue_job(job.id)
    except Exception as exc:
        job.error_message = f"failed to enqueue task: {exc}"[:4000]
        db.commit()

    return _upload_response(
        document,
        job,
        duplicate=False,
    )


@router.post(
    "/{document_id}/reparse",
    response_model=IngestionJobResponse,
)
def reparse_document(
    document_id: int,
    db: Session = Depends(get_db),
) -> IngestionJobResponse:
    document = db.get(DocumentVersion, document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="document not found",
        )

    idempotency_key = (
        f"parse:{document.file_hash}:{PARSER_CONFIG_VERSION}"
    )
    job = db.scalar(
        select(IngestionJob).where(
            IngestionJob.idempotency_key == idempotency_key
        )
    )

    if job is None:
        job = IngestionJob(
            document_version=document,
            job_type="parse",
            stage="queued",
            status="pending",
            input_hash=document.file_hash,
            idempotency_key=idempotency_key,
            parser_config_hash=PARSER_CONFIG_HASH,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
    elif job.status == "succeeded":
        return IngestionJobResponse.model_validate(job)
    elif job.status == "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="current parser version is already running",
        )
    else:
        job.status = "pending"
        job.stage = "queued"
        job.error_message = None
        job.started_at = None
        job.completed_at = None
        db.commit()
        db.refresh(job)

    try:
        _enqueue_job(job.id)
    except Exception as exc:
        job.error_message = f"failed to enqueue task: {exc}"[:4000]
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="failed to enqueue ingestion task",
        ) from exc

    return IngestionJobResponse.model_validate(job)


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
