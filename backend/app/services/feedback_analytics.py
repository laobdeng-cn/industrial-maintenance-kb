from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from math import sqrt

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.feedback import QueryLog, ReviewQueueItem
from app.services.embedding import embed_texts


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _percentage(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(part / total * 100.0, 2)


def _review_age_hours(created_at: datetime, *, now: datetime) -> float:
    delta = now - _as_utc(created_at)
    return round(max(0.0, delta.total_seconds() / 3600.0), 2)


def _review_resolution_hours(created_at: datetime, updated_at: datetime) -> float:
    delta = _as_utc(updated_at) - _as_utc(created_at)
    return max(0.0, delta.total_seconds() / 3600.0)


def _sla_state(age_hours: float, sla_hours: float, status: str) -> str:
    if status != "pending":
        return "resolved"
    if age_hours > sla_hours:
        return "overdue"
    if age_hours >= sla_hours * 0.75:
        return "due_soon"
    return "on_track"


def _window_start(days: int) -> datetime:
    now = _utc_now()
    start_date = (now - timedelta(days=days - 1)).date()
    return datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)


def _load_logs(db: Session, *, days: int) -> list[QueryLog]:
    since = _window_start(days)
    return list(
        db.scalars(
            select(QueryLog)
            .options(
                selectinload(QueryLog.feedback),
                selectinload(QueryLog.review_item),
                selectinload(QueryLog.equipment_model),
            )
            .where(QueryLog.created_at >= since)
            .order_by(QueryLog.created_at.asc(), QueryLog.id.asc())
        ).all()
    )


def _load_review_logs(db: Session, *, days: int) -> list[QueryLog]:
    since = _window_start(days)
    return list(
        db.scalars(
            select(QueryLog)
            .join(ReviewQueueItem, ReviewQueueItem.query_log_id == QueryLog.id)
            .options(
                selectinload(QueryLog.feedback),
                selectinload(QueryLog.review_item),
                selectinload(QueryLog.equipment_model),
            )
            .where(
                or_(
                    ReviewQueueItem.status == "pending",
                    ReviewQueueItem.updated_at >= since,
                )
            )
            .order_by(ReviewQueueItem.created_at.asc(), ReviewQueueItem.id.asc())
        ).all()
    )


def build_feedback_analytics(
    db: Session,
    *,
    days: int,
    sla_hours: float,
) -> dict:
    now = _utc_now()
    logs = _load_logs(db, days=days)
    review_logs = _load_review_logs(db, days=days)

    helpful_count = 0
    unhelpful_count = 0
    grounded_count = 0
    latency_total = 0
    decision_counts: Counter[str] = Counter()
    equipment_counts: Counter[str] = Counter()
    equipment_labels: dict[str, str] = {}

    trend: dict[str, dict[str, int]] = {}
    start_date = _window_start(days).date()
    for offset in range(days):
        day = start_date + timedelta(days=offset)
        trend[day.isoformat()] = {
            "total_queries": 0,
            "helpful": 0,
            "unhelpful": 0,
            "review_created": 0,
        }

    for log in logs:
        grounded_count += int(log.grounded)
        latency_total += int(log.latency_ms or 0)
        decision_counts[log.decision_source or "unknown"] += 1

        equipment_key = str(log.equipment_model_id)
        equipment = log.equipment_model
        equipment_label = (
            f"{equipment.model_code} · {equipment.manufacturer}"
            if equipment is not None
            else f"Equipment #{log.equipment_model_id}"
        )
        equipment_labels[equipment_key] = equipment_label
        equipment_counts[equipment_key] += 1

        day_key = _as_utc(log.created_at).date().isoformat()
        if day_key in trend:
            trend[day_key]["total_queries"] += 1

        feedback = log.feedback
        if feedback is not None:
            if feedback.rating == "helpful":
                helpful_count += 1
                if day_key in trend:
                    trend[day_key]["helpful"] += 1
            elif feedback.rating == "unhelpful":
                unhelpful_count += 1
                if day_key in trend:
                    trend[day_key]["unhelpful"] += 1

    review_items: list[dict] = []
    review_total = 0
    review_pending = 0
    review_overdue = 0
    review_due_soon = 0
    review_resolved = 0
    review_sla_met = 0
    review_sla_breached = 0
    oldest_pending_hours: float | None = None

    for log in review_logs:
        review = log.review_item
        if review is None:
            continue

        review_total += 1
        review_day = _as_utc(review.created_at).date().isoformat()
        if review_day in trend:
            trend[review_day]["review_created"] += 1

        feedback = log.feedback
        age_hours = _review_age_hours(review.created_at, now=now)
        due_at = _as_utc(review.created_at) + timedelta(hours=sla_hours)
        state = _sla_state(age_hours, sla_hours, review.status)

        if review.status == "pending":
            review_pending += 1
            oldest_pending_hours = (
                age_hours
                if oldest_pending_hours is None
                else max(oldest_pending_hours, age_hours)
            )
            if state == "overdue":
                review_overdue += 1
            elif state == "due_soon":
                review_due_soon += 1
        else:
            review_resolved += 1
            resolution_hours = _review_resolution_hours(review.created_at, review.updated_at)
            if resolution_hours <= sla_hours:
                review_sla_met += 1
            else:
                review_sla_breached += 1

        review_items.append(
            {
                "review_id": review.id,
                "query_log_id": log.id,
                "query": log.query,
                "equipment_model_id": log.equipment_model_id,
                "status": review.status,
                "created_at": review.created_at,
                "due_at": due_at,
                "age_hours": age_hours,
                "sla_hours": sla_hours,
                "sla_state": state,
                "feedback_rating": feedback.rating if feedback is not None else None,
                "feedback_reason": feedback.reason if feedback is not None else None,
            }
        )

    review_items.sort(
        key=lambda item: (
            item["status"] != "pending",
            item["sla_state"] != "overdue",
            -float(item["age_hours"]),
        )
    )

    total_queries = len(logs)
    feedback_total = helpful_count + unhelpful_count
    resolved_for_sla = review_sla_met + review_sla_breached

    decision_sources = [
        {
            "key": key,
            "label": key,
            "count": count,
            "percentage": _percentage(count, total_queries),
        }
        for key, count in decision_counts.most_common()
    ]

    equipment_models = [
        {
            "key": key,
            "label": equipment_labels.get(key, key),
            "count": count,
            "percentage": _percentage(count, total_queries),
        }
        for key, count in equipment_counts.most_common()
    ]

    return {
        "window_days": days,
        "sla_hours": sla_hours,
        "total_queries": total_queries,
        "grounded_count": grounded_count,
        "refused_count": total_queries - grounded_count,
        "feedback_total": feedback_total,
        "helpful_count": helpful_count,
        "unhelpful_count": unhelpful_count,
        "helpful_rate": (
            round(helpful_count / feedback_total * 100.0, 2)
            if feedback_total
            else None
        ),
        "avg_latency_ms": (
            round(latency_total / total_queries, 1)
            if total_queries
            else None
        ),
        "review_total": review_total,
        "review_pending": review_pending,
        "review_overdue": review_overdue,
        "review_due_soon": review_due_soon,
        "review_resolved": review_resolved,
        "review_sla_met": review_sla_met,
        "review_sla_breached": review_sla_breached,
        "review_sla_compliance_rate": (
            round(review_sla_met / resolved_for_sla * 100.0, 2)
            if resolved_for_sla
            else None
        ),
        "oldest_pending_hours": oldest_pending_hours,
        "decision_sources": decision_sources,
        "equipment_models": equipment_models,
        "trend": [
            {"date": date, **values}
            for date, values in sorted(trend.items())
        ],
        "review_sla_items": review_items,
    }


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def _centroid(vector_sum: list[float], count: int) -> list[float]:
    if count <= 0:
        return vector_sum
    return [value / count for value in vector_sum]


def build_query_clusters(
    db: Session,
    *,
    days: int,
    limit: int,
    similarity_threshold: float,
    only_problematic: bool,
) -> dict:
    logs = list(reversed(_load_logs(db, days=days)))
    if only_problematic:
        logs = [
            log
            for log in logs
            if (log.feedback is not None and log.feedback.rating == "unhelpful")
            or log.review_item is not None
        ]
    logs = logs[:limit]

    if not logs:
        return {
            "window_days": days,
            "similarity_threshold": similarity_threshold,
            "only_problematic": only_problematic,
            "sample_count": 0,
            "cluster_count": 0,
            "clusters": [],
        }

    vectors = embed_texts([log.query for log in logs])
    working_clusters: list[dict] = []

    for log, vector in zip(logs, vectors, strict=False):
        best_index: int | None = None
        best_score = -1.0

        for index, cluster in enumerate(working_clusters):
            score = _cosine_similarity(
                vector,
                _centroid(cluster["vector_sum"], cluster["count"]),
            )
            if score > best_score:
                best_score = score
                best_index = index

        if best_index is None or best_score < similarity_threshold:
            working_clusters.append(
                {
                    "vector_sum": list(vector),
                    "count": 1,
                    "members": [log],
                }
            )
            continue

        cluster = working_clusters[best_index]
        cluster["vector_sum"] = [
            current + value
            for current, value in zip(cluster["vector_sum"], vector, strict=False)
        ]
        cluster["count"] += 1
        cluster["members"].append(log)

    clusters: list[dict] = []
    now = _utc_now()
    sla_hours = settings.review_sla_hours

    for cluster in working_clusters:
        members: list[QueryLog] = cluster["members"]
        representative = members[0]
        unhelpful_count = sum(
            1
            for item in members
            if item.feedback is not None and item.feedback.rating == "unhelpful"
        )
        pending_review_count = sum(
            1
            for item in members
            if item.review_item is not None and item.review_item.status == "pending"
        )
        overdue_review_count = sum(
            1
            for item in members
            if item.review_item is not None
            and item.review_item.status == "pending"
            and _review_age_hours(item.review_item.created_at, now=now) > sla_hours
        )
        grounded_count = sum(1 for item in members if item.grounded)

        size = len(members)
        unhelpful_component = min(40.0, unhelpful_count * 20.0)
        pending_component = min(25.0, pending_review_count * 15.0)
        overdue_component = min(20.0, overdue_review_count * 20.0)
        recurrence_component = min(15.0, max(0, size - 1) * 5.0)
        priority_score = round(
            min(
                100.0,
                unhelpful_component
                + pending_component
                + overdue_component
                + recurrence_component,
            ),
            1,
        )

        if priority_score >= 70:
            priority_level = "urgent"
        elif priority_score >= 45:
            priority_level = "high"
        elif priority_score >= 20:
            priority_level = "medium"
        else:
            priority_level = "low"

        priority_reasons: list[str] = []
        if unhelpful_count:
            priority_reasons.append(f"{unhelpful_count} 条负反馈")
        if pending_review_count:
            priority_reasons.append(f"{pending_review_count} 条待审")
        if overdue_review_count:
            priority_reasons.append(f"{overdue_review_count} 条 SLA 超时")
        if size > 1:
            priority_reasons.append(f"{size} 条重复/相似问题")
        if not priority_reasons:
            priority_reasons.append("低频审查样本")

        member_ids = sorted(item.id for item in members)
        cluster_key = "trace-" + "-".join(str(item) for item in member_ids)

        promoted_case_ids = sorted(
            {
                item.review_item.promoted_case_id
                for item in members
                if item.review_item is not None
                and item.review_item.promoted_case_id is not None
            }
        )
        baseline_run_ids = sorted(
            {
                item.review_item.baseline_run_id
                for item in members
                if item.review_item is not None
                and item.review_item.baseline_run_id is not None
            }
        )
        last_regression_run_ids = sorted(
            {
                item.review_item.last_regression_run_id
                for item in members
                if item.review_item is not None
                and item.review_item.last_regression_run_id is not None
            }
        )

        clusters.append(
            {
                "cluster_key": cluster_key,
                "representative_query": representative.query,
                "size": size,
                "unhelpful_count": unhelpful_count,
                "pending_review_count": pending_review_count,
                "overdue_review_count": overdue_review_count,
                "grounded_count": grounded_count,
                "priority_score": priority_score,
                "priority_level": priority_level,
                "priority_reasons": priority_reasons,
                "equipment_model_ids": sorted(
                    {item.equipment_model_id for item in members}
                ),
                "promoted_case_ids": promoted_case_ids,
                "baseline_run_ids": baseline_run_ids,
                "last_regression_run_ids": last_regression_run_ids,
                "members": [
                    {
                        "query_log_id": item.id,
                        "query": item.query,
                        "equipment_model_id": item.equipment_model_id,
                        "grounded": item.grounded,
                        "feedback_rating": (
                            item.feedback.rating if item.feedback is not None else None
                        ),
                        "review_id": (
                            item.review_item.id if item.review_item is not None else None
                        ),
                        "review_status": (
                            item.review_item.status if item.review_item is not None else None
                        ),
                        "promoted_case_id": (
                            item.review_item.promoted_case_id
                            if item.review_item is not None
                            else None
                        ),
                        "baseline_run_id": (
                            item.review_item.baseline_run_id
                            if item.review_item is not None
                            else None
                        ),
                        "last_regression_run_id": (
                            item.review_item.last_regression_run_id
                            if item.review_item is not None
                            else None
                        ),
                        "top_final_score": item.top_final_score,
                        "top_rerank_score": item.top_rerank_score,
                        "decision_source": item.decision_source,
                        "citation_count": len(item.citations or []),
                        "hit_count": len(item.hits or []),
                        "latency_ms": item.latency_ms,
                        "created_at": item.created_at,
                    }
                    for item in members
                ],
            }
        )

    clusters.sort(
        key=lambda item: (
            item["priority_score"],
            item["unhelpful_count"],
            item["pending_review_count"],
            item["size"],
        ),
        reverse=True,
    )

    for index, cluster in enumerate(clusters, start=1):
        cluster["cluster_id"] = index

    return {
        "window_days": days,
        "similarity_threshold": similarity_threshold,
        "only_problematic": only_problematic,
        "sample_count": len(logs),
        "cluster_count": len(clusters),
        "clusters": clusters,
    }
