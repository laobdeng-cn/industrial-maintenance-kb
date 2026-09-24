from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.evaluation import EvaluationCase, EvaluationRun
from app.models.feedback import QueryLog, ReviewQueueItem
from app.schemas.evaluation import EvaluationRunCreate
from app.schemas.feedback import ClusterBatchReviewCreate, ClusterRegressionCreate
from app.services.evaluation import execute_evaluation_run, normalize_evaluation_query


def _load_query_logs(
    db: Session,
    query_log_ids: list[int],
) -> list[QueryLog]:
    rows = list(
        db.scalars(
            select(QueryLog)
            .options(
                selectinload(QueryLog.feedback),
                selectinload(QueryLog.review_item),
            )
            .where(QueryLog.id.in_(query_log_ids))
            .order_by(QueryLog.id.asc())
        ).all()
    )
    found_ids = {row.id for row in rows}
    missing = [item for item in query_log_ids if item not in found_ids]
    if missing:
        raise ValueError(f"query logs not found: {missing}")
    return rows


def _ensure_review_item(
    db: Session,
    query_log: QueryLog,
) -> tuple[ReviewQueueItem, bool]:
    item = query_log.review_item
    if item is not None:
        return item, False

    item = ReviewQueueItem(
        query_log_id=query_log.id,
        status="pending",
    )
    db.add(item)
    db.flush()
    query_log.review_item = item
    return item, True


def _existing_case_for_query_log(
    db: Session,
    query_log: QueryLog,
) -> EvaluationCase | None:
    normalized = normalize_evaluation_query(query_log.query)
    candidates = db.scalars(
        select(EvaluationCase).where(
            EvaluationCase.equipment_model_id == query_log.equipment_model_id
        )
    ).all()
    return next(
        (
            case
            for case in candidates
            if normalize_evaluation_query(case.query) == normalized
        ),
        None,
    )


def _citation_ids(query_log: QueryLog) -> list[str]:
    return list(
        dict.fromkeys(
            str(citation.get("evidence_id"))
            for citation in (query_log.citations or [])
            if citation.get("evidence_id")
        )
    )


def _promote_query_log(
    db: Session,
    *,
    query_log: QueryLog,
    review_item: ReviewQueueItem,
    reviewer_note: str | None,
) -> int:
    existing = _existing_case_for_query_log(db, query_log)
    if existing is None:
        citation_ids = _citation_ids(query_log)
        if query_log.grounded and not citation_ids:
            raise ValueError(
                f"grounded trace #{query_log.id} has no citation evidence"
            )

        case = EvaluationCase(
            query=query_log.query,
            equipment_model_id=query_log.equipment_model_id,
            expected_evidence_ids=citation_ids if query_log.grounded else [],
            allowed_citation_evidence_ids=citation_ids if query_log.grounded else [],
            expected_answerable=query_log.grounded,
            notes=(
                f"Promoted from Phase D.3 query trace #{query_log.id}. "
                "Batch-reviewed from a feedback cluster; verify the evidence labels "
                "before using this case as a long-term benchmark."
            ),
        )
        db.add(case)
        db.flush()
        case_id = case.id
    else:
        case_id = existing.id

    review_item.status = "accepted"
    review_item.promoted_case_id = case_id
    if reviewer_note is not None:
        review_item.reviewer_note = reviewer_note
    return case_id


def batch_review_cluster(
    db: Session,
    payload: ClusterBatchReviewCreate,
) -> dict:
    logs = _load_query_logs(db, payload.query_log_ids)
    reviews: list[ReviewQueueItem] = []
    created_review_count = 0
    promoted_case_ids: list[int] = []

    if payload.action == "promote":
        # Validate grounded traces up front so the batch stays atomic.
        for log in logs:
            if (
                log.grounded
                and _existing_case_for_query_log(db, log) is None
                and not _citation_ids(log)
            ):
                raise ValueError(
                    f"grounded trace #{log.id} has no citation evidence; "
                    "review evidence before batch promotion"
                )

    for log in logs:
        review, created = _ensure_review_item(db, log)
        created_review_count += int(created)

        if payload.action == "promote":
            promoted_case_ids.append(
                _promote_query_log(
                    db,
                    query_log=log,
                    review_item=review,
                    reviewer_note=payload.reviewer_note,
                )
            )
        elif payload.action == "ignore":
            review.status = "ignored"
            if payload.reviewer_note is not None:
                review.reviewer_note = payload.reviewer_note
        elif payload.action == "pending":
            review.status = "pending"
            if payload.reviewer_note is not None:
                review.reviewer_note = payload.reviewer_note
        else:
            raise ValueError(f"unsupported batch review action: {payload.action}")

        reviews.append(review)

    promoted_case_ids = list(dict.fromkeys(promoted_case_ids))
    db.commit()

    baseline_run_id: int | None = None
    if payload.action == "promote" and payload.create_baseline and promoted_case_ids:
        baseline = execute_evaluation_run(
            db=db,
            payload=EvaluationRunCreate(
                top_k=payload.top_k,
                case_ids=promoted_case_ids,
            ),
        )
        baseline_run_id = baseline.id

        for review in reviews:
            if review.promoted_case_id in promoted_case_ids:
                review.baseline_run_id = baseline_run_id
                review.last_regression_run_id = None
        db.commit()

    for review in reviews:
        db.refresh(review)

    return {
        "action": payload.action,
        "processed_count": len(reviews),
        "created_review_count": created_review_count,
        "promoted_case_ids": promoted_case_ids,
        "baseline_run_id": baseline_run_id,
        "reviews": reviews,
    }


def _resolve_baseline_run_id(
    reviews: list[ReviewQueueItem],
    requested_baseline_run_id: int | None,
) -> int:
    if requested_baseline_run_id is not None:
        return requested_baseline_run_id

    baseline_ids = {
        review.baseline_run_id
        for review in reviews
        if review.baseline_run_id is not None
    }
    if not baseline_ids:
        raise ValueError(
            "cluster has no baseline run; batch promote it with create_baseline=true first"
        )
    if len(baseline_ids) > 1:
        raise ValueError(
            "selected traces reference multiple baseline runs; specify baseline_run_id explicitly"
        )
    return next(iter(baseline_ids))


def run_cluster_regression(
    db: Session,
    payload: ClusterRegressionCreate,
) -> dict:
    logs = _load_query_logs(db, payload.query_log_ids)
    reviews: list[ReviewQueueItem] = []

    for log in logs:
        review = log.review_item
        if review is None or review.promoted_case_id is None:
            raise ValueError(
                f"trace #{log.id} is not promoted to Golden Set"
            )
        reviews.append(review)

    case_ids = list(
        dict.fromkeys(
            review.promoted_case_id
            for review in reviews
            if review.promoted_case_id is not None
        )
    )
    baseline_run_id = _resolve_baseline_run_id(
        reviews,
        payload.baseline_run_id,
    )

    baseline = db.scalar(
        select(EvaluationRun)
        .options(selectinload(EvaluationRun.results))
        .where(EvaluationRun.id == baseline_run_id)
    )
    if baseline is None:
        raise ValueError(f"baseline run #{baseline_run_id} not found")

    baseline_case_ids = {
        result.case_id
        for result in baseline.results
        if result.case_id is not None
    }
    missing_cases = [
        case_id for case_id in case_ids if case_id not in baseline_case_ids
    ]
    if missing_cases:
        raise ValueError(
            f"baseline run #{baseline_run_id} does not contain cases {missing_cases}"
        )

    candidate = execute_evaluation_run(
        db=db,
        payload=EvaluationRunCreate(
            top_k=payload.top_k,
            case_ids=case_ids,
            rough_recall_limit=payload.rough_recall_limit,
            vector_weight=payload.vector_weight,
            rerank_weight=payload.rerank_weight,
            grounding_min_final_score=payload.grounding_min_final_score,
            grounding_min_rerank_score=payload.grounding_min_rerank_score,
        ),
    )

    for review in reviews:
        review.last_regression_run_id = candidate.id
    db.commit()

    return {
        "baseline_run_id": baseline_run_id,
        "candidate_run_id": candidate.id,
        "case_ids": case_ids,
        "candidate_metrics": candidate.metrics,
        "comparison_path": (
            "/api/evaluation/runs/compare"
            f"?baseline_run_id={baseline_run_id}"
            f"&candidate_run_id={candidate.id}"
        ),
    }
