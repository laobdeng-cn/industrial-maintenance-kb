from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.models.document import DocumentVersion
from app.models.indexing import IndexGeneration
from app.schemas.search import IndexGenerationResponse
from app.services.indexing import (
    IndexingValidationError,
    index_document_now,
)


router = APIRouter(
    prefix="/api/indexing",
    tags=["indexing"],
)


@router.post(
    "/documents/{document_id}",
    response_model=IndexGenerationResponse,
)
def index_document(
    document_id: int,
    db: Session = Depends(get_db),
) -> IndexGenerationResponse:
    if db.get(DocumentVersion, document_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="document not found",
        )

    try:
        generation = index_document_now(
            db=db,
            document_id=document_id,
        )
    except IndexingValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"indexing failed: {exc}",
        ) from exc

    return IndexGenerationResponse.model_validate(generation)


@router.get(
    "/documents/{document_id}",
    response_model=IndexGenerationResponse,
)
def get_document_index(
    document_id: int,
    db: Session = Depends(get_db),
) -> IndexGenerationResponse:
    if db.get(DocumentVersion, document_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="document not found",
        )

    generation = db.scalar(
        select(IndexGeneration)
        .where(IndexGeneration.document_version_id == document_id)
        .order_by(IndexGeneration.updated_at.desc(), IndexGeneration.id.desc())
        .limit(1)
    )
    if generation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="document has not been indexed",
        )

    return IndexGenerationResponse.model_validate(generation)
