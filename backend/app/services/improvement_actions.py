from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.evaluation import EvaluationRun
from app.models.feedback import (
    ImprovementAction,
    ImprovementActionChangeSet,
    ImprovementActionVerification,
    ReviewQueueItem,
)
from app.schemas.evaluation import EvaluationRunCreate
from app.schemas.feedback import (
    ImprovementActionCreate,
    ImprovementActionUpdate,
    ImprovementCandidateRunCreate,
    ImprovementChangeSetCreate,
    ImprovementRegressionLink,
)
from app.services.evaluation import compare_evaluation_results, execute_evaluation_run


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


def _latest_change_set(
    db: Session,
    action_id: int,
) -> ImprovementActionChangeSet | None:
    return db.scalar(
        select(ImprovementActionChangeSet)
        .where(ImprovementActionChangeSet.action_id == action_id)
        .order_by(
            ImprovementActionChangeSet.sequence.desc(),
            ImprovementActionChangeSet.id.desc(),
        )
        .limit(1)
    )


def _latest_unverified_change_set(
    db: Session,
    action_id: int,
) -> ImprovementActionChangeSet | None:
    change_set = _latest_change_set(db, action_id)
    if change_set is None:
        return None
    verification_id = db.scalar(
        select(ImprovementActionVerification.id)
        .where(
            ImprovementActionVerification.action_id == action_id,
            ImprovementActionVerification.change_set_id == change_set.id,
        )
        .order_by(ImprovementActionVerification.id.desc())
        .limit(1)
    )
    return None if verification_id is not None else change_set


def _has_verification_history(db: Session, action_id: int) -> bool:
    return (
        db.scalar(
            select(ImprovementActionVerification.id)
            .where(ImprovementActionVerification.action_id == action_id)
            .limit(1)
        )
        is not None
    )


def _ensure_fixed_baseline(
    db: Session,
    item: ImprovementAction,
    requested_baseline_run_id: int | None,
) -> None:
    if (
        requested_baseline_run_id is None
        or item.baseline_run_id is None
        or requested_baseline_run_id == item.baseline_run_id
    ):
        return
    if item.candidate_run_id is not None or _has_verification_history(db, item.id):
        raise ValueError(
            f"baseline run is fixed at #{item.baseline_run_id} after verification; "
            "create a new Improvement Action to use another baseline"
        )


def _record_verification(
    db: Session,
    *,
    item: ImprovementAction,
    baseline_run_id: int,
    candidate_run_id: int,
    regression_status: str,
    regression_summary: dict,
    metrics_snapshot: dict | None,
    automated: bool,
) -> ImprovementActionVerification:
    existing = db.scalar(
        select(ImprovementActionVerification).where(
            ImprovementActionVerification.action_id == item.id,
            ImprovementActionVerification.candidate_run_id == candidate_run_id,
        )
    )
    change_set = _latest_unverified_change_set(db, item.id)
    now = datetime.now(timezone.utc)

    if existing is not None:
        existing.baseline_run_id = baseline_run_id
        existing.regression_status = regression_status
        existing.matched_case_count = int(
            regression_summary.get("matched_case_count") or 0
        )
        existing.metrics_snapshot = metrics_snapshot
        existing.regression_summary = regression_summary
        existing.automated = automated
        existing.verified_at = now
        if existing.change_set_id is None and change_set is not None:
            existing.change_set_id = change_set.id
        return existing

    verification = ImprovementActionVerification(
        action_id=item.id,
        change_set_id=change_set.id if change_set is not None else None,
        baseline_run_id=baseline_run_id,
        candidate_run_id=candidate_run_id,
        regression_status=regression_status,
        matched_case_count=int(
            regression_summary.get("matched_case_count") or 0
        ),
        metrics_snapshot=metrics_snapshot,
        regression_summary=regression_summary,
        automated=automated,
        verified_at=now,
    )
    db.add(verification)
    db.flush()
    return verification


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
    if (
        item.regression_status is not None
        and item.baseline_run_id is not None
        and item.candidate_run_id is not None
        and item.regression_summary is not None
    ):
        candidate = db.get(EvaluationRun, item.candidate_run_id)
        _record_verification(
            db,
            item=item,
            baseline_run_id=item.baseline_run_id,
            candidate_run_id=item.candidate_run_id,
            regression_status=item.regression_status,
            regression_summary=item.regression_summary,
            metrics_snapshot=candidate.metrics if candidate is not None else None,
            automated=False,
        )
    db.commit()
    db.refresh(item)
    return item


def create_improvement_change_set(
    db: Session,
    action_id: int,
    payload: ImprovementChangeSetCreate,
) -> ImprovementActionChangeSet:
    item = _get_action_or_error(db, action_id)
    if item.baseline_run_id is None:
        raise ValueError(
            "improvement action has no baseline run; establish a baseline "
            "before recording an implementation"
        )

    pending_change_set = _latest_unverified_change_set(db, item.id)
    if pending_change_set is not None:
        raise ValueError(
            f"change set #{pending_change_set.sequence} is still awaiting verification; "
            "verify it before recording another implementation"
        )

    next_sequence = int(
        db.scalar(
            select(
                func.coalesce(
                    func.max(ImprovementActionChangeSet.sequence),
                    0,
                )
                + 1
            ).where(ImprovementActionChangeSet.action_id == item.id)
        )
        or 1
    )

    change_set = ImprovementActionChangeSet(
        action_id=item.id,
        sequence=next_sequence,
        change_type=payload.change_type,
        target=payload.target,
        before_version=payload.before_version,
        after_version=payload.after_version,
        summary=payload.summary,
        details=payload.details,
        implemented_by=payload.implemented_by or item.owner,
        implemented_at=payload.implemented_at or datetime.now(timezone.utc),
    )
    db.add(change_set)

    # A new implementation means the Action is active again, while the
    # previous candidate/regression remains visible as the latest verified
    # state until Verify Again creates a new verification record.
    item.status = "in_progress"
    item.closed_at = None

    db.commit()
    db.refresh(change_set)
    return change_set


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
    _ensure_fixed_baseline(db, item, baseline_run_id)
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
        if (
            item.regression_status is not None
            and item.baseline_run_id is not None
            and item.candidate_run_id is not None
            and item.regression_summary is not None
        ):
            candidate = db.get(EvaluationRun, item.candidate_run_id)
            _record_verification(
                db,
                item=item,
                baseline_run_id=item.baseline_run_id,
                candidate_run_id=item.candidate_run_id,
                regression_status=item.regression_status,
                regression_summary=item.regression_summary,
                metrics_snapshot=candidate.metrics if candidate is not None else None,
                automated=False,
            )

    db.commit()
    db.refresh(item)
    return item


def link_improvement_regression(
    db: Session,
    action_id: int,
    payload: ImprovementRegressionLink,
) -> ImprovementAction:
    item = _get_action_or_error(db, action_id)
    relevant_case_ids = _action_case_ids(db, item)
    if item.source_query_log_ids and not relevant_case_ids:
        raise ValueError(
            "linked traces have no promoted Golden Set cases; "
            "promote/review them before linking a regression run"
        )

    _ensure_fixed_baseline(db, item, payload.baseline_run_id)
    if (
        _has_verification_history(db, item.id)
        and payload.candidate_run_id != item.candidate_run_id
        and _latest_unverified_change_set(db, item.id) is None
    ):
        raise ValueError(
            "manual re-verification requires a pending Change Set; "
            "record the implementation before linking a new Candidate"
        )

    status, summary = _regression_snapshot(
        db,
        baseline_run_id=payload.baseline_run_id,
        candidate_run_id=payload.candidate_run_id,
        relevant_case_ids=relevant_case_ids,
    )
    item.baseline_run_id = payload.baseline_run_id
    item.candidate_run_id = payload.candidate_run_id
    item.regression_status = status
    item.regression_summary = summary

    candidate = db.get(EvaluationRun, payload.candidate_run_id)
    _record_verification(
        db,
        item=item,
        baseline_run_id=payload.baseline_run_id,
        candidate_run_id=payload.candidate_run_id,
        regression_status=status,
        regression_summary=summary,
        metrics_snapshot=candidate.metrics if candidate is not None else None,
        automated=False,
    )

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


def run_improvement_candidate(
    db: Session,
    action_id: int,
    payload: ImprovementCandidateRunCreate,
) -> dict:
    """Run a post-action candidate against the action's promoted Golden Set cases.

    Retrieval/Gate parameters are copied from the Baseline snapshot so the
    Candidate isolates the current application / prompt behavior rather than
    silently changing evaluation parameters.
    """
    item = _get_action_or_error(db, action_id)
    if item.status == "closed":
        raise ValueError(
            "closed improvement action cannot run a new candidate; reopen it first"
        )
    if item.baseline_run_id is None:
        raise ValueError(
            "improvement action has no baseline run; establish a baseline first"
        )

    if (
        _has_verification_history(db, item.id)
        and _latest_unverified_change_set(db, item.id) is None
    ):
        raise ValueError(
            "this action already has verification history; record a new Change Set "
            "before Verify Again"
        )

    relevant_case_ids = _action_case_ids(db, item)
    if not relevant_case_ids:
        raise ValueError(
            "linked traces have no promoted Golden Set cases; "
            "promote/review them before running a candidate"
        )

    baseline = db.scalar(
        select(EvaluationRun)
        .options(selectinload(EvaluationRun.results))
        .where(EvaluationRun.id == item.baseline_run_id)
    )
    if baseline is None:
        raise ValueError(f"baseline run #{item.baseline_run_id} not found")

    baseline_case_ids = {
        result.case_id
        for result in baseline.results
        if result.case_id is not None
    }
    missing_cases = [
        case_id
        for case_id in relevant_case_ids
        if case_id not in baseline_case_ids
    ]
    if missing_cases:
        raise ValueError(
            f"baseline run #{baseline.id} does not contain cases {missing_cases}"
        )

    snapshot = baseline.parameter_snapshot or {}
    top_k = int(snapshot.get("top_k") or baseline.top_k or 5)

    vector_weight = snapshot.get("vector_weight")
    rerank_weight = snapshot.get("rerank_weight")
    if vector_weight is None or rerank_weight is None:
        vector_weight = None
        rerank_weight = None

    run_payload = EvaluationRunCreate(
        top_k=top_k,
        case_ids=relevant_case_ids,
        rough_recall_limit=snapshot.get("rough_recall_limit"),
        vector_weight=vector_weight,
        rerank_weight=rerank_weight,
        grounding_min_final_score=snapshot.get("grounding_min_final_score"),
        grounding_min_rerank_score=snapshot.get(
            "grounding_min_rerank_score"
        ),
    )

    if item.status != "in_progress":
        item.status = "in_progress"
        item.closed_at = None
        db.flush()

    candidate = execute_evaluation_run(
        db=db,
        payload=run_payload,
    )

    # Keep the Review Queue trace linked to the latest verification run.
    reviews = list(
        db.scalars(
            select(ReviewQueueItem).where(
                ReviewQueueItem.query_log_id.in_(item.source_query_log_ids),
                ReviewQueueItem.promoted_case_id.in_(relevant_case_ids),
            )
        ).all()
    )
    for review in reviews:
        review.last_regression_run_id = candidate.id

    regression_status, regression_summary = _regression_snapshot(
        db,
        baseline_run_id=baseline.id,
        candidate_run_id=candidate.id,
        relevant_case_ids=relevant_case_ids,
    )
    item.candidate_run_id = candidate.id
    item.regression_status = regression_status
    item.regression_summary = regression_summary

    verification = _record_verification(
        db,
        item=item,
        baseline_run_id=baseline.id,
        candidate_run_id=candidate.id,
        regression_status=regression_status,
        regression_summary=regression_summary,
        metrics_snapshot=candidate.metrics,
        automated=True,
    )

    if (
        payload.close_on_no_regression
        and regression_status in {"improved", "unchanged"}
    ):
        item.status = "closed"
        item.closed_at = datetime.now(timezone.utc)
        item.close_note = (
            "Candidate verification completed with fixed baseline parameters; "
            f"Baseline #{baseline.id} -> Candidate #{candidate.id}: "
            f"{regression_status}. No new regression detected."
        )
    else:
        item.status = "in_progress"
        item.closed_at = None

    db.commit()
    db.refresh(item)

    return {
        "baseline_run_id": baseline.id,
        "candidate_run_id": candidate.id,
        "case_ids": relevant_case_ids,
        "regression_status": regression_status,
        "candidate_metrics": candidate.metrics,
        "comparison_path": (
            "/api/evaluation/runs/compare"
            f"?baseline_run_id={baseline.id}"
            f"&candidate_run_id={candidate.id}"
        ),
        "verification": verification,
        "action": item,
    }


def list_improvement_actions(
    db: Session,
    *,
    status_filter: str | None,
    limit: int,
) -> dict:
    statement = (
        select(ImprovementAction)
        .options(
            selectinload(ImprovementAction.change_sets),
            selectinload(ImprovementAction.verifications),
        )
        .order_by(ImprovementAction.id.desc())
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
