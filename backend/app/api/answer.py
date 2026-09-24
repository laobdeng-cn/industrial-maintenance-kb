from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.models.feedback import QueryLog
from app.schemas.search import GroundedAnswerResponse, SearchRequest
from app.services.answering import answer_question
from app.services.deepseek import (
    DeepSeekConfigurationError,
    DeepSeekRequestError,
)


router = APIRouter(prefix="/api/answer", tags=["answer"])


@router.post("", response_model=GroundedAnswerResponse)
def grounded_answer(
    payload: SearchRequest,
    db: Session = Depends(get_db),
) -> GroundedAnswerResponse:
    try:
        started_at = perf_counter()
        result = answer_question(payload=payload, db=db)
        latency_ms = max(1, int((perf_counter() - started_at) * 1000))

        query_log = QueryLog(
            query=result.query,
            equipment_model_id=result.equipment_model_id,
            grounded=result.grounded,
            answer=result.answer,
            refusal_reason=result.refusal_reason,
            decision_source=result.decision_source,
            top_final_score=result.top_final_score,
            top_rerank_score=result.top_rerank_score,
            citations=[item.model_dump(mode="json") for item in result.citations],
            hits=[item.model_dump(mode="json") for item in result.hits],
            latency_ms=latency_ms,
        )
        db.add(query_log)
        db.commit()
        db.refresh(query_log)
        return result.model_copy(update={"query_log_id": query_log.id})
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
