from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.deps import get_db
from app.models.evaluation import EvaluationCase
from app.models.feedback import AnswerFeedback, QueryLog, ReviewQueueItem
from app.schemas.feedback import AnswerFeedbackCreate, QueryLogResponse, ReviewQueueResponse, ReviewQueueUpdate
from app.services.evaluation import normalize_evaluation_query


router = APIRouter(prefix="/api/feedback", tags=["feedback"])


def _get_query_log_or_404(db: Session, query_log_id: int) -> QueryLog:
    item = db.scalar(
        select(QueryLog)
        .options(selectinload(QueryLog.feedback), selectinload(QueryLog.review_item))
        .where(QueryLog.id == query_log_id)
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="query log not found")
    return item


def _get_review_or_404(db: Session, review_id: int) -> ReviewQueueItem:
    item = db.get(ReviewQueueItem, review_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="review queue item not found")
    return item


@router.get("/query-logs", response_model=list[QueryLogResponse])
def list_query_logs(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[QueryLog]:
    return list(
        db.scalars(
            select(QueryLog)
            .options(selectinload(QueryLog.feedback), selectinload(QueryLog.review_item))
            .order_by(QueryLog.id.desc())
            .limit(limit)
        ).all()
    )


@router.get("/review-queue", response_model=list[QueryLogResponse])
def list_review_queue(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[QueryLog]:
    statement = (
        select(QueryLog)
        .join(ReviewQueueItem, ReviewQueueItem.query_log_id == QueryLog.id)
        .options(selectinload(QueryLog.feedback), selectinload(QueryLog.review_item))
        .order_by(ReviewQueueItem.id.desc())
        .limit(limit)
    )
    if status_filter is not None:
        if status_filter not in {"pending", "accepted", "ignored"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="status must be pending, accepted, or ignored",
            )
        statement = statement.where(ReviewQueueItem.status == status_filter)
    return list(db.scalars(statement).all())


@router.post("/query-logs/{query_log_id}/feedback", response_model=QueryLogResponse)
def submit_feedback(
    query_log_id: int,
    payload: AnswerFeedbackCreate,
    db: Session = Depends(get_db),
) -> QueryLog:
    query_log = _get_query_log_or_404(db, query_log_id)
    feedback = query_log.feedback
    if feedback is None:
        feedback = AnswerFeedback(
            query_log_id=query_log.id,
            rating=payload.rating,
            reason=payload.reason,
            comment=payload.comment,
        )
        db.add(feedback)
    else:
        feedback.rating = payload.rating
        feedback.reason = payload.reason
        feedback.comment = payload.comment

    review_item = query_log.review_item
    if payload.rating == "unhelpful":
        if review_item is None:
            db.add(ReviewQueueItem(query_log_id=query_log.id, status="pending"))
        elif review_item.status == "ignored":
            review_item.status = "pending"
    elif review_item is not None and review_item.status == "pending":
        review_item.status = "ignored"
        review_item.reviewer_note = (
            review_item.reviewer_note
            or "Auto-closed after feedback was changed to helpful."
        )

    db.commit()
    return _get_query_log_or_404(db, query_log.id)


@router.put("/review-queue/{review_id}", response_model=ReviewQueueResponse)
def update_review_item(
    review_id: int,
    payload: ReviewQueueUpdate,
    db: Session = Depends(get_db),
) -> ReviewQueueItem:
    item = _get_review_or_404(db, review_id)
    item.status = payload.status
    item.reviewer_note = payload.reviewer_note
    db.commit()
    db.refresh(item)
    return item


@router.post("/review-queue/{review_id}/promote", response_model=ReviewQueueResponse)
def promote_review_item(
    review_id: int,
    db: Session = Depends(get_db),
) -> ReviewQueueItem:
    item = _get_review_or_404(db, review_id)
    query_log = db.get(QueryLog, item.query_log_id)
    if query_log is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="query log not found")

    normalized = normalize_evaluation_query(query_log.query)
    existing_cases = db.scalars(
        select(EvaluationCase).where(EvaluationCase.equipment_model_id == query_log.equipment_model_id)
    ).all()
    existing = next(
        (case for case in existing_cases if normalize_evaluation_query(case.query) == normalized),
        None,
    )

    if existing is None:
        citation_ids = list(
            dict.fromkeys(
                citation.get("evidence_id")
                for citation in (query_log.citations or [])
                if citation.get("evidence_id")
            )
        )
        if query_log.grounded and not citation_ids:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="grounded trace has no citation evidence; review evidence before promoting to Golden Set",
            )
        evaluation_case = EvaluationCase(
            query=query_log.query,
            equipment_model_id=query_log.equipment_model_id,
            expected_evidence_ids=citation_ids if query_log.grounded else [],
            allowed_citation_evidence_ids=citation_ids if query_log.grounded else [],
            expected_answerable=query_log.grounded,
            notes=(
                f"Promoted from Phase D.1 query trace #{query_log.id}. "
                "Review the auto-selected citation evidence before using this case as a long-term benchmark."
            ),
        )
        db.add(evaluation_case)
        db.flush()
        item.promoted_case_id = evaluation_case.id
    else:
        item.promoted_case_id = existing.id

    item.status = "accepted"
    db.commit()
    db.refresh(item)
    return item
