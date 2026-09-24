from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.evaluation import EvaluationRun
from app.models.feedback import ImprovementAction, ReviewQueueItem
from app.schemas.feedback import (
    ImprovementActionCreate,
    ImprovementActionUpdate,
    ImprovementRegressionLink,
)
from app.services.evaluation import compare_evaluation_results


ACTIVE_STATUSES = {"open", "in_progress", "blocked", "done"}
TERMINAL_STATUSES = {"done", "closed"}

STATUS_TRANSITIONS = {
    "open": {"open", "in_progress", "blocked", "done", "closed"},
    "in_progress": {"open", "in_progress", "blocked", "done", "closed"},
    "blocked": {"open", "in_progress", "blocked", "done", "closed"},
    "done": {"in_progress", "done", "closed"},
    "closed": {"in_progress", "closed"},
}


def _get_action_or_error(db: Session, action_id: int) -> ImprovementAction:
    item = db.get(ImprovementAction, action_id)
    if item is None:
        raise ValueError(f"improvement action #{action_id} not found")
    return item


def _ensure_run(db: Session, run_id: int | None, label: str) -> None:
    if run_id is None:
        return
    if db.get(EvaluationRun, run_id) is None:
        raise ValueError(f"{label} run #{run_id} not found")


def _action_case_ids(
    db: Session,
    item: ImprovementAction,
) -> list[int]:
    if not item.source_query_log_ids:
        return []
    return list(
        dict.fromkeys(
            case_id
            for case_id in db.scalars(
                select(ReviewQueueItem.promoted_case_id).where(
                    ReviewQueueItem.query_log_id.in_(item.source_query_log_ids),
                    ReviewQueueItem.promoted_case_id.is_not(None),
                )
            ).all()
            if case_id is not None
        )
    )


def _regression_snapshot(
    db: Session,
    *,
    baseline_run_id: int,
    candidate_run_id: int,
    relevant_case_ids: list[int] | None = None,
) -> tuple[str, dict]:
    if baseline_run_id == candidate_run_id:
        raise ValueError("baseline and candidate runs must be different")

    baseline = db.scalar(
        select(EvaluationRun)
        .options(selectinload(EvaluationRun.results))
        .where(EvaluationRun.id == baseline_run_id)
    )
    candidate = db.scalar(
        select(EvaluationRun)
        .options(selectinload(EvaluationRun.results))
        .where(EvaluationRun.id == candidate_run_id)
    )
    if baseline is None:
        raise ValueError(f"baseline run #{baseline_run_id} not found")
    if candidate is None:
        raise ValueError(f"candidate run #{candidate_run_id} not found")

    baseline_by_case = {
        result.case_id: result
        for result in baseline.results
        if result.case_id is not None
    }
    candidate_by_case = {
        result.case_id: result
        for result in candidate.results
        if result.case_id is not None
    }
    common_case_ids = sorted(set(baseline_by_case) & set(candidate_by_case))
    if relevant_case_ids:
        common_case_ids = [
            case_id
            for case_id in common_case_ids
            if case_id in set(relevant_case_ids)
        ]
    if not common_case_ids:
        raise ValueError("baseline and candidate runs have no comparable cases")

    counts = {
        "regressed": 0,
        "improved": 0,
        "mixed": 0,
        "unchanged": 0,
        "incomparable": 0,
    }
    samples: list[dict] = []

    for case_id in common_case_ids:
        comparison = compare_evaluation_results(
            baseline_by_case[case_id],
            candidate_by_case[case_id],
        )
        status = comparison["status"]
        counts[status] = counts.get(status, 0) + 1
        samples.append(
            {
                "case_id": case_id,
                "query": comparison["query"],
                "status": status,
                "regression_reasons": comparison["regression_reasons"],
                "improvement_reasons": comparison["improvement_reasons"],
            }
        )

    if counts["regressed"] > 0:
        overall = "regressed"
    elif counts["mixed"] > 0:
        overall = "mixed"
    elif counts["improved"] > 0:
        overall = "improved"
    elif counts["unchanged"] == len(common_case_ids):
        overall = "unchanged"
    else:
        overall = "incomparable"

    return overall, {
        "baseline_run_id": baseline_run_id,
        "candidate_run_id": candidate_run_id,
        "matched_case_count": len(common_case_ids),
        "counts": counts,
        "samples": samples[:20],
    }


def _apply_regression_if_ready(
    db: Session,
    item: ImprovementAction,
) -> None:
    if item.baseline_run_id is None or item.candidate_run_id is None:
        item.regression_status = None
        item.regression_summary = None
        return

    status, summary = _regression_snapshot(
        db,
        baseline_run_id=item.baseline_run_id,
        candidate_run_id=item.candidate_run_id,
        relevant_case_ids=_action_case_ids(db, item),
    )
    item.regression_status = status
    item.regression_summary = summary


def create_improvement_action(
    db: Session,
    payload: ImprovementActionCreate,
) -> ImprovementAction:
    duplicate_stmt = select(ImprovementAction).where(
        ImprovementAction.cluster_key == payload.cluster_key,
        ImprovementAction.action_type == payload.action_type,
        ImprovementAction.title == payload.title,
        ImprovementAction.status != "closed",
    )
    if payload.source_recommendation_index is not None:
        duplicate_stmt = duplicate_stmt.where(
            ImprovementAction.source_recommendation_index
            == payload.source_recommendation_index
        )

    existing = db.scalar(duplicate_stmt.order_by(ImprovementAction.id.desc()))
    if existing is not None:
        raise ValueError(
            f"active improvement action already exists: #{existing.id}"
        )

    _ensure_run(db, payload.baseline_run_id, "baseline")
    _ensure_run(db, payload.candidate_run_id, "candidate")

    item = ImprovementAction(
        **payload.model_dump(),
        status="open",
    )
    db.add(item)
    db.flush()
    _apply_regression_if_ready(db, item)
    db.commit()
    db.refresh(item)
    return item


def update_improvement_action(
    db: Session,
    action_id: int,
    payload: ImprovementActionUpdate,
) -> ImprovementAction:
    item = _get_action_or_error(db, action_id)
    changes = payload.model_dump(exclude_unset=True)

    requested_status = changes.get("status")
    if requested_status is not None:
        allowed = STATUS_TRANSITIONS.get(item.status, {item.status})
        if requested_status not in allowed:
            raise ValueError(
                f"invalid status transition: {item.status} -> {requested_status}"
            )

    baseline_run_id = changes.get("baseline_run_id", item.baseline_run_id)
    candidate_run_id = changes.get("candidate_run_id", item.candidate_run_id)
    _ensure_run(db, baseline_run_id, "baseline")
    _ensure_run(db, candidate_run_id, "candidate")

    for key, value in changes.items():
        setattr(item, key, value)

    if requested_status == "closed":
        item.closed_at = datetime.now(timezone.utc)
    elif requested_status is not None and item.closed_at is not None:
        item.closed_at = None

    if "baseline_run_id" in changes or "candidate_run_id" in changes:
        _apply_regression_if_ready(db, item)

    db.commit()
    db.refresh(item)
    return item


def link_improvement_regression(
    db: Session,
    action_id: int,
    payload: ImprovementRegressionLink,
) -> ImprovementAction:
    item = _get_action_or_error(db, action_id)
    status, summary = _regression_snapshot(
        db,
        baseline_run_id=payload.baseline_run_id,
        candidate_run_id=payload.candidate_run_id,
        relevant_case_ids=_action_case_ids(db, item),
    )
    item.baseline_run_id = payload.baseline_run_id
    item.candidate_run_id = payload.candidate_run_id
    item.regression_status = status
    item.regression_summary = summary

    if payload.close_on_no_regression and status in {"improved", "unchanged"}:
        item.status = "closed"
        item.closed_at = datetime.now(timezone.utc)
        item.close_note = (
            item.close_note
            or f"Auto-closed after regression result: {status}."
        )

    db.commit()
    db.refresh(item)
    return item


def list_improvement_actions(
    db: Session,
    *,
    status_filter: str | None,
    limit: int,
) -> dict:
    statement = select(ImprovementAction).order_by(
        ImprovementAction.id.desc()
    )
    if status_filter is not None:
        statement = statement.where(ImprovementAction.status == status_filter)
    actions = list(db.scalars(statement.limit(limit)).all())

    all_actions = list(
        db.scalars(
            select(ImprovementAction).order_by(ImprovementAction.id.desc())
        ).all()
    )
    now = datetime.now(timezone.utc)

    def is_overdue(item: ImprovementAction) -> bool:
        if item.due_at is None or item.status in TERMINAL_STATUSES:
            return False
        due_at = item.due_at
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=timezone.utc)
        return due_at < now

    summary = {
        "total": len(all_actions),
        "open": sum(item.status == "open" for item in all_actions),
        "in_progress": sum(item.status == "in_progress" for item in all_actions),
        "blocked": sum(item.status == "blocked" for item in all_actions),
        "done": sum(item.status == "done" for item in all_actions),
        "closed": sum(item.status == "closed" for item in all_actions),
        "overdue": sum(is_overdue(item) for item in all_actions),
        "with_regression": sum(
            item.regression_status is not None for item in all_actions
        ),
    }
    return {"summary": summary, "actions": actions}
