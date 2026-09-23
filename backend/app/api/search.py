from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.schemas.search import SearchRequest, SearchResponse
from app.services.retrieval import retrieve_evidence


router = APIRouter(prefix="/api/search", tags=["search"])


@router.post("", response_model=SearchResponse)
def semantic_search(
    payload: SearchRequest,
    db: Session = Depends(get_db),
) -> SearchResponse:
    return retrieve_evidence(payload=payload, db=db)
