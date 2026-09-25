from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from statistics import mean

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.feedback import ImprovementAction, QueryLog


VERIFIED_REGRESSION_STATUSES = {"improved", "unchanged", "regressed", "mixed"}
COMPLETED_STATUSES = {"done", "closed"}
TERMINAL_STATUSES = {"done", "closed"}

OUTCOME_POINTS = {
    "improved": 70.0,
    "unchanged": 35.0,
    "mixed": 5.0,
    "regressed": -60.0,
    "incomparable": 0.0,
    None: 0.0,
}

ROI_FORMULA = (
    "ROI index = clamp((outcome_points + stability_points - recurrence_penalty "
    "- overdue_penalty) / cycle_cost_factor, -100, 100). "
    "This is an engineering impact index, not a financial ROI."
)

RECURRENCE_DEFINITION = (
    "A recurrence candidate is a post-close query from the same equipment family "
    "whose normalized query similarity meets the threshold and that received "
    "unhelpful feedback or re-entered pending review."
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _window_start(days: int) -> datetime:
    return _utc_now() - timedelta(days=days)


def _normalize_query(value: str) -> str:
    return "".join(
        char.lower()
        for char in value.strip()
        if char.isalnum()
    )


def _query_similarity(left: str, right: str) -> float:
    left_norm = _normalize_query(left)
    right_norm = _normalize_query(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def _percentage(part: int, total: int) -> float | None:
    if total <= 0:
        return None
    return round(part / total * 100.0, 2)


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(mean(values), 2)


def _cycle_hours(item: ImprovementAction, now: datetime) -> float | None:
    end = _as_utc(item.closed_at)
    if end is None and item.status == "done":
        end = _as_utc(item.updated_at)
    start = _as_utc(item.created_at)
    if start is None or end is None:
        return None
    return round(max(0.0, (end - start).total_seconds() / 3600.0), 2)


def _is_overdue(item: ImprovementAction, now: datetime) -> bool:
    due = _as_utc(item.due_at)
    if due is None or item.status in TERMINAL_STATUSES:
        return False
    return due < now


def _source_equipment_ids(
    source_logs_by_id: dict[int, QueryLog],
    item: ImprovementAction,
) -> set[int]:
    return {
        source_logs_by_id[log_id].equipment_model_id
        for log_id in item.source_query_log_ids
        if log_id in source_logs_by_id
    }


def _recurrence_events(
    item: ImprovementAction,
    *,
    source_logs_by_id: dict[int, QueryLog],
    candidate_logs: list[QueryLog],
    similarity_threshold: float,
) -> list[dict]:
    closed_at = _as_utc(item.closed_at)
    if closed_at is None:
        return []

    equipment_ids = _source_equipment_ids(source_logs_by_id, item)
    events: list[dict] = []

    for log in candidate_logs:
        created_at = _as_utc(log.created_at)
        if created_at is None or created_at <= closed_at:
            continue
        if equipment_ids and log.equipment_model_id not in equipment_ids:
            continue

        feedback_rating = log.feedback.rating if log.feedback is not None else None
        review_status = log.review_item.status if log.review_item is not None else None
        problematic = feedback_rating == "unhelpful" or review_status == "pending"
        if not problematic:
            continue

        similarity = _query_similarity(item.source_query, log.query)
        if similarity < similarity_threshold:
            continue

        events.append(
            {
                "query_log_id": log.id,
                "query": log.query,
                "created_at": log.created_at,
                "similarity": round(similarity, 4),
                "feedback_rating": feedback_rating,
                "review_status": review_status,
            }
        )

    events.sort(key=lambda event: event["created_at"])
    return events


def _roi_components(
    item: ImprovementAction,
    *,
    regression_status: str | None,
    recurrence_count: int,
    cycle_hours: float | None,
    overdue: bool,
) -> dict:
    outcome_points = OUTCOME_POINTS.get(regression_status, 0.0)

    stability_points = 0.0
    verified = regression_status in VERIFIED_REGRESSION_STATUSES
    if verified and item.status == "closed" and recurrence_count == 0:
        stability_points = 20.0
    elif verified and item.status == "done" and recurrence_count == 0:
        stability_points = 10.0

    recurrence_penalty = float(min(60, recurrence_count * 20))
    overdue_penalty = 10.0 if overdue else 0.0

    # One week is the neutral engineering cycle. Very long cycles reduce the
    # impact index gradually rather than pretending to be a monetary cost.
    normalized_cycle = min((cycle_hours or 0.0) / 168.0, 2.0)
    cycle_cost_factor = round(1.0 + normalized_cycle * 0.25, 4)

    raw_impact = (
        outcome_points
        + stability_points
        - recurrence_penalty
        - overdue_penalty
    )
    roi_index = max(-100.0, min(100.0, raw_impact / cycle_cost_factor))

    return {
        "outcome_points": round(outcome_points, 2),
        "stability_points": round(stability_points, 2),
        "recurrence_penalty": round(recurrence_penalty, 2),
        "overdue_penalty": round(overdue_penalty, 2),
        "cycle_cost_factor": cycle_cost_factor,
        "raw_impact": round(raw_impact, 2),
        "roi_index": round(roi_index, 2),
        "formula": ROI_FORMULA,
    }


def _build_breakdowns(
    rows: list[dict],
    key_name: str,
) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        raw = row[key_name]
        key = str(raw or "unassigned")
        grouped[key].append(row)

    result: list[dict] = []
    for key, items in grouped.items():
        verified = [
            item
            for item in items
            if item["regression_status"] in VERIFIED_REGRESSION_STATUSES
        ]
        improved = sum(item["regression_status"] == "improved" for item in items)
        unchanged = sum(item["regression_status"] == "unchanged" for item in items)
        regressed = sum(item["regression_status"] == "regressed" for item in items)
        mixed = sum(item["regression_status"] == "mixed" for item in items)
        recurrence_actions = sum(item["recurrence_count"] > 0 for item in items)
        roi_values = [
            float(item["roi"]["roi_index"])
            for item in items
            if item["regression_status"] in VERIFIED_REGRESSION_STATUSES
        ]

        result.append(
            {
                "key": key,
                "label": key.replace("_", " ").title(),
                "action_count": len(items),
                "verified_count": len(verified),
                "improved_count": improved,
                "unchanged_count": unchanged,
                "regressed_count": regressed,
                "mixed_count": mixed,
                "recurrence_action_count": recurrence_actions,
                "improvement_rate": _percentage(improved, len(verified)),
                "non_regression_rate": _percentage(
                    improved + unchanged,
                    len(verified),
                ),
                "recurrence_rate": _percentage(
                    recurrence_actions,
                    sum(item["status"] == "closed" for item in items),
                ),
                "avg_roi_index": _avg(roi_values),
            }
        )

    result.sort(
        key=lambda item: (
            -(item["action_count"]),
            -(item["avg_roi_index"] or -999.0),
            item["key"],
        )
    )
    return result


def build_improvement_effectiveness(
    db: Session,
    *,
    days: int,
    recurrence_similarity_threshold: float,
) -> dict:
    now = _utc_now()
    since = _window_start(days)

    actions = list(
        db.scalars(
            select(ImprovementAction)
            .options(selectinload(ImprovementAction.verifications))
            .where(
                or_(
                    ImprovementAction.created_at >= since,
                    ImprovementAction.updated_at >= since,
                    ImprovementAction.closed_at >= since,
                    ImprovementAction.status.in_(["open", "in_progress", "blocked"]),
                )
            )
            .order_by(ImprovementAction.id.desc())
        ).all()
    )

    source_log_ids = {
        log_id
        for item in actions
        for log_id in (item.source_query_log_ids or [])
    }
    source_logs = (
        list(
            db.scalars(
                select(QueryLog).where(QueryLog.id.in_(source_log_ids))
            ).all()
        )
        if source_log_ids
        else []
    )
    source_logs_by_id = {log.id: log for log in source_logs}

    closed_actions = [item for item in actions if item.closed_at is not None]
    earliest_close = min(
        (_as_utc(item.closed_at) for item in closed_actions if item.closed_at is not None),
        default=None,
    )

    candidate_logs: list[QueryLog] = []
    if earliest_close is not None:
        candidate_logs = list(
            db.scalars(
                select(QueryLog)
                .options(
                    selectinload(QueryLog.feedback),
                    selectinload(QueryLog.review_item),
                )
                .where(QueryLog.created_at > earliest_close)
                .order_by(QueryLog.created_at.asc(), QueryLog.id.asc())
            ).all()
        )

    action_rows: list[dict] = []
    recurrence_event_count = 0
    overdue_count = 0

    for item in actions:
        latest_verification = (
            item.verifications[-1]
            if item.verifications
            else None
        )
        effective_regression_status = (
            latest_verification.regression_status
            if latest_verification is not None
            else item.regression_status
        )
        effective_candidate_run_id = (
            latest_verification.candidate_run_id
            if latest_verification is not None
            else item.candidate_run_id
        )

        overdue = _is_overdue(item, now)
        overdue_count += int(overdue)
        cycle_hours = _cycle_hours(item, now)
        recurrence_events = _recurrence_events(
            item,
            source_logs_by_id=source_logs_by_id,
            candidate_logs=candidate_logs,
            similarity_threshold=recurrence_similarity_threshold,
        )
        recurrence_count = len(recurrence_events)
        recurrence_event_count += recurrence_count
        roi = _roi_components(
            item,
            regression_status=effective_regression_status,
            recurrence_count=recurrence_count,
            cycle_hours=cycle_hours,
            overdue=overdue,
        )

        action_rows.append(
            {
                "action_id": item.id,
                "title": item.title,
                "root_cause": item.root_cause,
                "owner": item.owner,
                "priority": item.priority,
                "status": item.status,
                "created_at": item.created_at,
                "closed_at": item.closed_at,
                "cycle_hours": cycle_hours,
                "baseline_run_id": item.baseline_run_id,
                "candidate_run_id": effective_candidate_run_id,
                "regression_status": effective_regression_status,
                "recurrence_count": recurrence_count,
                "first_recurrence_at": (
                    recurrence_events[0]["created_at"]
                    if recurrence_events
                    else None
                ),
                "last_recurrence_at": (
                    recurrence_events[-1]["created_at"]
                    if recurrence_events
                    else None
                ),
                "recurrence_events": recurrence_events[:20],
                "roi": roi,
            }
        )

    verified = [
        row
        for row in action_rows
        if row["regression_status"] in VERIFIED_REGRESSION_STATUSES
    ]
    completed = [
        row
        for row in action_rows
        if row["status"] in COMPLETED_STATUSES
    ]
    improved_count = sum(row["regression_status"] == "improved" for row in action_rows)
    unchanged_count = sum(row["regression_status"] == "unchanged" for row in action_rows)
    regressed_count = sum(row["regression_status"] == "regressed" for row in action_rows)
    mixed_count = sum(row["regression_status"] == "mixed" for row in action_rows)
    incomparable_count = sum(row["regression_status"] == "incomparable" for row in action_rows)
    recurrence_action_count = sum(row["recurrence_count"] > 0 for row in action_rows)
    cycle_values = [
        float(row["cycle_hours"])
        for row in completed
        if row["cycle_hours"] is not None
    ]
    roi_values = [
        float(row["roi"]["roi_index"])
        for row in verified
    ]

    # Highest recurrence risk first; otherwise show low ROI actions first because
    # those are the most actionable items for D.6.
    action_rows.sort(
        key=lambda row: (
            -row["recurrence_count"],
            row["roi"]["roi_index"],
            -row["action_id"],
        )
    )

    return {
        "window_days": days,
        "recurrence_similarity_threshold": recurrence_similarity_threshold,
        "recurrence_definition": RECURRENCE_DEFINITION,
        "roi_definition": ROI_FORMULA,
        "summary": {
            "action_count": len(action_rows),
            "completed_action_count": len(completed),
            "verified_action_count": len(verified),
            "improved_count": improved_count,
            "unchanged_count": unchanged_count,
            "regressed_count": regressed_count,
            "mixed_count": mixed_count,
            "incomparable_count": incomparable_count,
            "unverified_count": len(action_rows) - len(verified),
            "overdue_count": overdue_count,
            "improvement_rate": _percentage(improved_count, len(verified)),
            "non_regression_rate": _percentage(
                improved_count + unchanged_count,
                len(verified),
            ),
            "regression_rate": _percentage(regressed_count, len(verified)),
            "avg_cycle_hours": _avg(cycle_values),
            "recurrence_action_count": recurrence_action_count,
            "recurrence_event_count": recurrence_event_count,
            "recurrence_rate": _percentage(
                recurrence_action_count,
                len(closed_actions),
            ),
            "avg_roi_index": _avg(roi_values),
        },
        "by_root_cause": _build_breakdowns(action_rows, "root_cause"),
        "by_priority": _build_breakdowns(action_rows, "priority"),
        "by_owner": _build_breakdowns(action_rows, "owner"),
        "actions": action_rows,
    }
