from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.deps import get_db
from app.schemas.search import (
    GroundedAnswerResponse,
    GroundedCitationResponse,
    SearchRequest,
)
from app.services.deepseek import (
    DeepSeekConfigurationError,
    DeepSeekRequestError,
    InvalidCitationError,
    generate_grounded_answer,
)
from app.services.retrieval import retrieve_evidence


router = APIRouter(prefix="/api/answer", tags=["answer"])


def _insufficient_message(query: str) -> str:
    if any("\u4e00" <= char <= "\u9fff" for char in query):
        return "现有知识库证据不足，无法可靠回答该问题。"
    return (
        "The available knowledge-base evidence is insufficient "
        "to answer this question reliably."
    )


def _citation(index: int, hit) -> GroundedCitationResponse:
    return GroundedCitationResponse(
        index=index,
        evidence_id=hit.evidence_id,
        document_id=hit.document_id,
        block_id=hit.block_id,
        title=hit.title,
        version=hit.version,
        section_path=hit.section_path,
        page_start=hit.page_start,
        page_end=hit.page_end,
        asset_id=hit.asset_id,
        text=hit.text,
    )


@router.post("", response_model=GroundedAnswerResponse)
def grounded_answer(
    payload: SearchRequest,
    db: Session = Depends(get_db),
) -> GroundedAnswerResponse:
    retrieval = retrieve_evidence(payload=payload, db=db)

    top_final_score = (
        retrieval.hits[0].final_score
        if retrieval.hits
        else None
    )

    if (
        not retrieval.hits
        or top_final_score is None
        or top_final_score < settings.grounding_min_final_score
    ):
        return GroundedAnswerResponse(
            query=payload.query,
            equipment_model_id=payload.equipment_model_id,
            grounded=False,
            answer=_insufficient_message(payload.query),
            refusal_reason="insufficient_evidence",
            model=None,
            grounding_threshold=settings.grounding_min_final_score,
            top_final_score=top_final_score,
            embedding_model=retrieval.embedding_model,
            collection_name=retrieval.collection_name,
            rough_recall_limit=retrieval.rough_recall_limit,
            citations=[],
            hits=retrieval.hits,
        )

    try:
        answer, citation_numbers = generate_grounded_answer(
            query=payload.query,
            hits=retrieval.hits,
        )
    except DeepSeekConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except DeepSeekRequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except InvalidCitationError:
        return GroundedAnswerResponse(
            query=payload.query,
            equipment_model_id=payload.equipment_model_id,
            grounded=False,
            answer=_insufficient_message(payload.query),
            refusal_reason="invalid_or_missing_citations",
            model=settings.deepseek_model,
            grounding_threshold=settings.grounding_min_final_score,
            top_final_score=top_final_score,
            embedding_model=retrieval.embedding_model,
            collection_name=retrieval.collection_name,
            rough_recall_limit=retrieval.rough_recall_limit,
            citations=[],
            hits=retrieval.hits,
        )

    citations = [
        _citation(index, retrieval.hits[index - 1])
        for index in citation_numbers
    ]

    return GroundedAnswerResponse(
        query=payload.query,
        equipment_model_id=payload.equipment_model_id,
        grounded=True,
        answer=answer,
        refusal_reason=None,
        model=settings.deepseek_model,
        grounding_threshold=settings.grounding_min_final_score,
        top_final_score=top_final_score,
        embedding_model=retrieval.embedding_model,
        collection_name=retrieval.collection_name,
        rough_recall_limit=retrieval.rough_recall_limit,
        citations=citations,
        hits=retrieval.hits,
    )
