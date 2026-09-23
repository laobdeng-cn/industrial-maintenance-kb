from datetime import datetime, timezone

from qdrant_client import models
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.document import DocumentVersion
from app.models.indexing import IndexGeneration
from app.services.embedding import embed_texts
from app.services.vector_store import (
    delete_document_points,
    ensure_collection,
    upload_points,
)


class IndexingValidationError(ValueError):
    pass


def _embedding_text(
    document: DocumentVersion,
    block_text: str,
    section_path: str | None,
) -> str:
    parts = [document.title]

    if section_path and section_path.strip() != document.title.strip():
        parts.append(section_path.strip())

    parts.append(block_text.strip())
    return "\n\n".join(parts)


def _get_document_for_indexing(
    db: Session,
    document_id: int,
) -> DocumentVersion | None:
    return db.scalar(
        select(DocumentVersion)
        .options(
            selectinload(DocumentVersion.equipment_models),
            selectinload(DocumentVersion.blocks),
        )
        .where(DocumentVersion.id == document_id)
    )


def _get_or_create_generation(
    db: Session,
    document: DocumentVersion,
) -> IndexGeneration:
    generation = db.scalar(
        select(IndexGeneration).where(
            IndexGeneration.document_version_id == document.id,
            IndexGeneration.embedding_model == settings.embedding_model,
        )
    )

    if generation is None:
        generation = IndexGeneration(
            document_version_id=document.id,
            embedding_model=settings.embedding_model,
            collection_name=settings.qdrant_collection,
            vector_size=settings.embedding_vector_size,
            status="pending",
        )
        db.add(generation)
        db.flush()

    return generation


def index_document_now(
    db: Session,
    document_id: int,
) -> IndexGeneration:
    document = _get_document_for_indexing(db, document_id)
    if document is None:
        raise IndexingValidationError("document not found")

    if document.status != "published":
        raise IndexingValidationError(
            "only published documents can be indexed"
        )

    equipment_model_ids = [
        model.id
        for model in document.equipment_models
    ]
    if not equipment_model_ids:
        raise IndexingValidationError(
            "document must be bound to at least one equipment model"
        )

    searchable_blocks = [
        block
        for block in document.blocks
        if block.text is not None and block.text.strip()
    ]
    if not searchable_blocks:
        raise IndexingValidationError(
            "document has no searchable text blocks"
        )

    generation = _get_or_create_generation(db, document)
    generation.status = "running"
    generation.point_count = 0
    generation.error_message = None
    generation.started_at = datetime.now(timezone.utc)
    generation.completed_at = None
    db.commit()

    try:
        ensure_collection()
        delete_document_points(document.id)

        texts = [
            _embedding_text(
                document=document,
                block_text=block.text or "",
                section_path=block.section_path,
            )
            for block in searchable_blocks
        ]
        vectors = embed_texts(texts)

        points: list[models.PointStruct] = []
        for block, vector in zip(searchable_blocks, vectors, strict=True):
            points.append(
                models.PointStruct(
                    id=block.id,
                    vector=vector,
                    payload={
                        "document_id": document.id,
                        "block_id": block.id,
                        "evidence_id": block.evidence_id,
                        "equipment_model_ids": equipment_model_ids,
                        "status": document.status,
                        "title": document.title,
                        "version": document.version,
                        "language": document.language,
                        "block_type": block.block_type,
                        "section_path": block.section_path,
                        "page_start": block.page_start,
                        "page_end": block.page_end,
                        "asset_id": block.asset_id,
                        "text": block.text,
                    },
                )
            )

        upload_points(points)

        generation = db.get(IndexGeneration, generation.id)
        if generation is None:
            raise RuntimeError("index generation disappeared")

        generation.status = "succeeded"
        generation.point_count = len(points)
        generation.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(generation)
        return generation
    except Exception as exc:
        db.rollback()

        failed_generation = db.get(IndexGeneration, generation.id)
        if failed_generation is not None:
            failed_generation.status = "failed"
            failed_generation.error_message = str(exc)[:4000]
            failed_generation.completed_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(failed_generation)

        raise
