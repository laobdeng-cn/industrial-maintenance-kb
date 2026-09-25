from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.db.deps import get_db
from app.models.evaluation import EvaluationCase
from app.models.feedback import AnswerFeedback, QueryLog, ReviewQueueItem
from app.schemas.feedback import (
    AnswerFeedbackCreate,
    ClusterBatchReviewCreate,
    ClusterBatchReviewResponse,
    ClusterDiagnosisResponse,
    ClusterRegressionCreate,
    ClusterRegressionResponse,
    FeedbackAnalyticsResponse,
    ImprovementActionCreate,
    ImprovementActionListResponse,
    ImprovementActionResponse,
    ImprovementCandidateRunCreate,
    ImprovementCandidateRunResponse,
    ImprovementEffectivenessResponse,
    ImprovementActionUpdate,
    ImprovementRegressionLink,
    QueryClusterDrilldownRequest,
    QueryClusterResponse,
    QueryLogResponse,
    ReviewQueueResponse,
    ReviewQueueUpdate,
)
from app.services.evaluation import normalize_evaluation_query
from app.services.feedback_analytics import build_feedback_analytics, build_query_clusters
from app.services.feedback_diagnosis import build_cluster_diagnostics
from app.services.feedback_workflow import batch_review_cluster, run_cluster_regression
from app.services.improvement_actions import (
    create_improvement_action,
    link_improvement_regression,
    list_improvement_actions,
    run_improvement_candidate,
    update_improvement_action,
)
from app.services.improvement_effectiveness import build_improvement_effectiveness


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


@router.get("/analytics", response_model=FeedbackAnalyticsResponse)
def feedback_analytics(
    days: int = Query(default=7, ge=1, le=90),
    sla_hours: float | None = Query(default=None, gt=0, le=720),
    db: Session = Depends(get_db),
) -> dict:
    return build_feedback_analytics(
        db,
        days=days,
        sla_hours=sla_hours or settings.review_sla_hours,
    )


@router.get("/clusters", response_model=QueryClusterResponse)
def feedback_clusters(
    days: int = Query(default=30, ge=1, le=180),
    limit: int = Query(default=100, ge=1, le=200),
    similarity_threshold: float | None = Query(default=None, ge=0.5, le=0.99),
    only_problematic: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return build_query_clusters(
            db,
            days=days,
            limit=limit,
            similarity_threshold=(
                similarity_threshold
                if similarity_threshold is not None
                else settings.feedback_cluster_similarity_threshold
            ),
            only_problematic=only_problematic,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"feedback clustering failed: {exc}",
        ) from exc


@router.get("/clusters/diagnostics", response_model=ClusterDiagnosisResponse)
def cluster_diagnostics(
    days: int = Query(default=30, ge=1, le=180),
    limit: int = Query(default=100, ge=1, le=200),
    similarity_threshold: float | None = Query(default=None, ge=0.5, le=0.99),
    only_problematic: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return build_cluster_diagnostics(
            db,
            days=days,
            limit=limit,
            similarity_threshold=(
                similarity_threshold
                if similarity_threshold is not None
                else settings.feedback_cluster_similarity_threshold
            ),
            only_problematic=only_problematic,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"feedback diagnosis failed: {exc}",
        ) from exc


@router.post("/clusters/drilldown", response_model=list[QueryLogResponse])
def cluster_drilldown(
    payload: QueryClusterDrilldownRequest,
    db: Session = Depends(get_db),
) -> list[QueryLog]:
    rows = list(
        db.scalars(
            select(QueryLog)
            .options(
                selectinload(QueryLog.feedback),
                selectinload(QueryLog.review_item),
            )
            .where(QueryLog.id.in_(payload.query_log_ids))
            .order_by(QueryLog.id.desc())
        ).all()
    )
    found_ids = {row.id for row in rows}
    missing = [item for item in payload.query_log_ids if item not in found_ids]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"query logs not found: {missing}",
        )
    return rows


@router.post(
    "/clusters/batch-review",
    response_model=ClusterBatchReviewResponse,
)
def cluster_batch_review(
    payload: ClusterBatchReviewCreate,
    db: Session = Depends(get_db),
) -> dict:
    try:
        return batch_review_cluster(db, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/clusters/regression",
    response_model=ClusterRegressionResponse,
)
def cluster_regression(
    payload: ClusterRegressionCreate,
    db: Session = Depends(get_db),
) -> dict:
    try:
        return run_cluster_regression(db, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/improvement-actions",
    response_model=ImprovementActionListResponse,
)
def improvement_actions(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=300),
    db: Session = Depends(get_db),
) -> dict:
    if status_filter is not None and status_filter not in {
        "open",
        "in_progress",
        "blocked",
        "done",
        "closed",
    }:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="status must be open, in_progress, blocked, done, or closed",
        )
    return list_improvement_actions(
        db,
        status_filter=status_filter,
        limit=limit,
    )


@router.get(
    "/improvement-actions/effectiveness",
    response_model=ImprovementEffectivenessResponse,
)
def improvement_action_effectiveness(
    days: int = Query(default=90, ge=1, le=365),
    recurrence_similarity_threshold: float = Query(
        default=0.72,
        ge=0.5,
        le=0.99,
    ),
    db: Session = Depends(get_db),
) -> dict:
    return build_improvement_effectiveness(
        db,
        days=days,
        recurrence_similarity_threshold=recurrence_similarity_threshold,
    )


@router.post(
    "/improvement-actions",
    response_model=ImprovementActionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_action(
    payload: ImprovementActionCreate,
    db: Session = Depends(get_db),
):
    try:
        return create_improvement_action(db, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.put(
    "/improvement-actions/{action_id}",
    response_model=ImprovementActionResponse,
)
def update_action(
    action_id: int,
    payload: ImprovementActionUpdate,
    db: Session = Depends(get_db),
):
    try:
        return update_improvement_action(db, action_id, payload)
    except ValueError as exc:
        message = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in message
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code=code, detail=message) from exc


@router.post(
    "/improvement-actions/{action_id}/run-candidate",
    response_model=ImprovementCandidateRunResponse,
)
def run_action_candidate(
    action_id: int,
    payload: ImprovementCandidateRunCreate,
    db: Session = Depends(get_db),
):
    try:
        return run_improvement_candidate(db, action_id, payload)
    except ValueError as exc:
        message = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in message
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code=code, detail=message) from exc


@router.post(
    "/improvement-actions/{action_id}/regression",
    response_model=ImprovementActionResponse,
)
def link_action_regression(
    action_id: int,
    payload: ImprovementRegressionLink,
    db: Session = Depends(get_db),
):
    try:
        return link_improvement_regression(db, action_id, payload)
    except ValueError as exc:
        message = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in message
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code=code, detail=message) from exc


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
