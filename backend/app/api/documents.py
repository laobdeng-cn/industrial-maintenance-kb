from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.parser import PARSER_CONFIG_HASH, PARSER_CONFIG_VERSION
from app.db.deps import get_db
from app.models.content import DocumentAsset, DocumentBlock
from app.models.document import DocumentVersion
from app.models.equipment import EquipmentModel
from app.models.ingestion import IngestionJob
from app.schemas.document import (
    DocumentAssetResponse,
    DocumentBlockResponse,
    DocumentEquipmentBindingRequest,
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


def _get_document_or_404(
    db: Session,
    document_id: int,
) -> DocumentVersion:
    document = db.scalar(
        select(DocumentVersion)
        .options(selectinload(DocumentVersion.equipment_models))
        .where(DocumentVersion.id == document_id)
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="document not found",
        )
    return document


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
        select(DocumentVersion)
        .options(selectinload(DocumentVersion.equipment_models))
        .where(DocumentVersion.file_hash == stored.sha256)
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
            select(DocumentVersion)
            .options(selectinload(DocumentVersion.equipment_models))
            .where(DocumentVersion.file_hash == stored.sha256)
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


@router.get(
    "",
    response_model=list[DocumentResponse],
)
def list_documents(
    db: Session = Depends(get_db),
) -> list[DocumentResponse]:
    documents = db.scalars(
        select(DocumentVersion)
        .options(selectinload(DocumentVersion.equipment_models))
        .order_by(DocumentVersion.created_at.desc(), DocumentVersion.id.desc())
    ).all()
    return [
        DocumentResponse.model_validate(document)
        for document in documents
    ]


@router.put(
    "/{document_id}/equipment-models",
    response_model=DocumentResponse,
)
def bind_document_equipment_models(
    document_id: int,
    payload: DocumentEquipmentBindingRequest,
    db: Session = Depends(get_db),
) -> DocumentResponse:
    document = _get_document_or_404(db, document_id)
    requested_ids = list(dict.fromkeys(payload.equipment_model_ids))

    if not requested_ids:
        document.equipment_models = []
        db.commit()
        db.refresh(document)
        return DocumentResponse.model_validate(document)

    models = db.scalars(
        select(EquipmentModel)
        .where(EquipmentModel.id.in_(requested_ids))
        .order_by(EquipmentModel.id.asc())
    ).all()

    found_ids = {model.id for model in models}
    missing_ids = [
        equipment_id
        for equipment_id in requested_ids
        if equipment_id not in found_ids
    ]
    if missing_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": "one or more equipment models were not found",
                "missing_ids": missing_ids,
            },
        )

    document.equipment_models = models
    db.commit()
    db.refresh(document)
    return DocumentResponse.model_validate(document)


@router.post(
    "/{document_id}/publish",
    response_model=DocumentResponse,
)
def publish_document(
    document_id: int,
    db: Session = Depends(get_db),
) -> DocumentResponse:
    document = _get_document_or_404(db, document_id)

    if document.status == "published":
        return DocumentResponse.model_validate(document)

    has_blocks = db.scalar(
        select(DocumentBlock.id)
        .where(DocumentBlock.document_version_id == document.id)
        .limit(1)
    )
    if has_blocks is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="document must be parsed successfully before publishing",
        )

    document.status = "published"
    document.published_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(document)
    return DocumentResponse.model_validate(document)


@router.post(
    "/{document_id}/archive",
    response_model=DocumentResponse,
)
def archive_document(
    document_id: int,
    db: Session = Depends(get_db),
) -> DocumentResponse:
    document = _get_document_or_404(db, document_id)
    document.status = "archived"
    db.commit()
    db.refresh(document)
    return DocumentResponse.model_validate(document)


@router.post(
    "/{document_id}/reparse",
    response_model=IngestionJobResponse,
)
def reparse_document(
    document_id: int,
    db: Session = Depends(get_db),
) -> IngestionJobResponse:
    document = _get_document_or_404(db, document_id)

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
    "/{document_id}/blocks",
    response_model=list[DocumentBlockResponse],
)
def list_document_blocks(
    document_id: int,
    db: Session = Depends(get_db),
) -> list[DocumentBlockResponse]:
    _get_document_or_404(db, document_id)
    blocks = db.scalars(
        select(DocumentBlock)
        .where(DocumentBlock.document_version_id == document_id)
        .order_by(DocumentBlock.ordinal.asc(), DocumentBlock.id.asc())
    ).all()

    return [
        DocumentBlockResponse.model_validate(block)
        for block in blocks
    ]


@router.get(
    "/{document_id}/assets",
    response_model=list[DocumentAssetResponse],
)
def list_document_assets(
    document_id: int,
    db: Session = Depends(get_db),
) -> list[DocumentAssetResponse]:
    _get_document_or_404(db, document_id)
    assets = db.scalars(
        select(DocumentAsset)
        .where(DocumentAsset.document_version_id == document_id)
        .order_by(DocumentAsset.page_number.asc().nullslast(), DocumentAsset.id.asc())
    ).all()

    return [
        DocumentAssetResponse.model_validate(asset)
        for asset in assets
    ]


@router.get(
    "/{document_id}/file",
)
def get_document_file(
    document_id: int,
    db: Session = Depends(get_db),
) -> FileResponse:
    document = _get_document_or_404(db, document_id)

    if not document.storage_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="document file is not available",
        )

    path = Path(settings.storage_root) / document.storage_path
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="document file is missing from storage",
        )

    return FileResponse(
        path=path,
        media_type="application/pdf",
        filename=document.original_filename or f"document-{document.id}.pdf",
    )


@router.get(
    "/{document_id}/assets/{asset_id}/file",
)
def get_document_asset_file(
    document_id: int,
    asset_id: int,
    db: Session = Depends(get_db),
) -> FileResponse:
    _get_document_or_404(db, document_id)

    asset = db.scalar(
        select(DocumentAsset).where(
            DocumentAsset.id == asset_id,
            DocumentAsset.document_version_id == document_id,
        )
    )
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="document asset not found",
        )

    path = Path(settings.storage_root) / asset.storage_path
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="document asset file is missing from storage",
        )

    return FileResponse(
        path=path,
        media_type=asset.mime_type or "application/octet-stream",
        filename=path.name,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
)
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
) -> DocumentResponse:
    return DocumentResponse.model_validate(
        _get_document_or_404(db, document_id)
    )
