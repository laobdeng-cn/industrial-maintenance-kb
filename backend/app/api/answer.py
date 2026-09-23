from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.schemas.search import GroundedAnswerResponse, SearchRequest
from app.services.answering import answer_question
from app.services.deepseek import (
    DeepSeekConfigurationError,
    DeepSeekRequestError,
    InvalidGroundedDecisionError,
)


router = APIRouter(prefix="/api/answer", tags=["answer"])


@router.post("", response_model=GroundedAnswerResponse)
def grounded_answer(
    payload: SearchRequest,
    db: Session = Depends(get_db),
) -> GroundedAnswerResponse:
    try:
        return answer_question(payload=payload, db=db)
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
    except InvalidGroundedDecisionError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="DeepSeek returned an invalid grounded decision",
        )
