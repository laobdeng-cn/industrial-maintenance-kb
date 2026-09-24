from itertools import product

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.deps import get_db
from app.models.equipment import EquipmentModel
from app.models.evaluation import EvaluationCase, EvaluationRun
from app.schemas.evaluation import (
    EvaluationCaseCreate,
    EvaluationCaseHygieneResponse,
    EvaluationCaseResponse,
    EvaluationCaseUpdate,
    EvaluationLeaderboardItem,
    EvaluationRunComparisonResponse,
    EvaluationRunCreate,
    EvaluationRunResponse,
    EvaluationRunSummaryResponse,
    EvaluationSweepCreate,
    EvaluationSweepResponse,
    ThresholdErrorAnalysisResponse,
)
from app.services.evaluation import (
    analyze_evaluation_case_hygiene,
    compare_evaluation_results,
    evaluation_issue_codes,
    execute_evaluation_run,
    normalize_evaluation_query,
)


router = APIRouter(
    prefix="/api/evaluation",
    tags=["evaluation"],
)


def _get_case_or_404(db: Session, case_id: int) -> EvaluationCase:
    case = db.get(EvaluationCase, case_id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="evaluation case not found",
        )
    return case


def _ensure_equipment(db: Session, equipment_model_id: int) -> None:
    if db.get(EquipmentModel, equipment_model_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="equipment model not found",
        )


def _apply_evidence_policy(values: dict) -> dict:
    expected_answerable = bool(values.get("expected_answerable", True))
    expected = list(dict.fromkeys(values.get("expected_evidence_ids") or []))
    allowed = list(
        dict.fromkeys(values.get("allowed_citation_evidence_ids") or [])
    )

    if not expected_answerable:
        expected = []
        allowed = []
    else:
        allowed = list(dict.fromkeys([*expected, *allowed]))

    values["expected_evidence_ids"] = expected
    values["allowed_citation_evidence_ids"] = allowed
    return values


def _find_case_collision(
    db: Session,
    *,
    query: str,
    equipment_model_id: int,
    exclude_case_id: int | None = None,
) -> EvaluationCase | None:
    normalized = normalize_evaluation_query(query)
    candidates = db.scalars(
        select(EvaluationCase).where(
            EvaluationCase.equipment_model_id == equipment_model_id
        )
    ).all()
    for candidate in candidates:
        if exclude_case_id is not None and candidate.id == exclude_case_id:
            continue
        if normalize_evaluation_query(candidate.query) == normalized:
            return candidate
    return None


@router.get(
    "/cases",
    response_model=list[EvaluationCaseResponse],
)
def list_cases(
    db: Session = Depends(get_db),
) -> list[EvaluationCase]:
    return list(
        db.scalars(
            select(EvaluationCase).order_by(EvaluationCase.id.desc())
        ).all()
    )


@router.get(
    "/cases/hygiene",
    response_model=EvaluationCaseHygieneResponse,
)
def case_hygiene(
    db: Session = Depends(get_db),
) -> dict:
    cases = list(
        db.scalars(select(EvaluationCase).order_by(EvaluationCase.id)).all()
    )
    return analyze_evaluation_case_hygiene(cases)


@router.post(
    "/cases",
    response_model=EvaluationCaseResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_case(
    payload: EvaluationCaseCreate,
    db: Session = Depends(get_db),
) -> EvaluationCase:
    _ensure_equipment(db, payload.equipment_model_id)

    collision = _find_case_collision(
        db,
        query=payload.query,
        equipment_model_id=payload.equipment_model_id,
    )
    if collision is not None:
        relationship = (
            "conflicts with"
            if collision.expected_answerable != payload.expected_answerable
            else "duplicates"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"evaluation case {relationship} existing case "
                f"#{collision.id}; edit or remove the existing case instead"
            ),
        )

    values = _apply_evidence_policy(payload.model_dump())
    case = EvaluationCase(**values)
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


@router.put(
    "/cases/{case_id}",
    response_model=EvaluationCaseResponse,
)
def update_case(
    case_id: int,
    payload: EvaluationCaseUpdate,
    db: Session = Depends(get_db),
) -> EvaluationCase:
    case = _get_case_or_404(db, case_id)
    changes = payload.model_dump(exclude_unset=True)

    if "equipment_model_id" in changes:
        _ensure_equipment(db, changes["equipment_model_id"])

    prospective = {
        "query": changes.get("query", case.query),
        "equipment_model_id": changes.get(
            "equipment_model_id",
            case.equipment_model_id,
        ),
        "expected_evidence_ids": changes.get(
            "expected_evidence_ids",
            case.expected_evidence_ids,
        ),
        "allowed_citation_evidence_ids": changes.get(
            "allowed_citation_evidence_ids",
            case.allowed_citation_evidence_ids,
        ),
        "expected_answerable": changes.get(
            "expected_answerable",
            case.expected_answerable,
        ),
        "notes": changes.get("notes", case.notes),
    }
    prospective = _apply_evidence_policy(prospective)

    identity_changed = (
        normalize_evaluation_query(prospective["query"])
        != normalize_evaluation_query(case.query)
        or prospective["equipment_model_id"] != case.equipment_model_id
    )

    # Existing duplicate groups are intentionally editable so operators can
    # repair evidence labels / answerability first and delete redundant rows
    # afterwards. Only introducing a new query+equipment collision is blocked.
    if identity_changed:
        collision = _find_case_collision(
            db,
            query=prospective["query"],
            equipment_model_id=prospective["equipment_model_id"],
            exclude_case_id=case.id,
        )
        if collision is not None:
            relationship = (
                "conflicts with"
                if collision.expected_answerable
                != prospective["expected_answerable"]
                else "duplicates"
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"evaluation case {relationship} existing case "
                    f"#{collision.id}; keep the existing query/equipment identity "
                    "while repairing this duplicate group, or remove the other "
                    "case first"
                ),
            )

    for key, value in prospective.items():
        setattr(case, key, value)

    db.commit()
    db.refresh(case)
    return case


@router.delete(
    "/cases/{case_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_case(
    case_id: int,
    db: Session = Depends(get_db),
) -> Response:
    case = _get_case_or_404(db, case_id)
    db.delete(case)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/runs",
    response_model=list[EvaluationRunSummaryResponse],
)
def list_runs(
    db: Session = Depends(get_db),
) -> list[EvaluationRun]:
    return list(
        db.scalars(
            select(EvaluationRun)
            .order_by(EvaluationRun.id.desc())
            .limit(30)
        ).all()
    )


def _get_run_or_404(db: Session, run_id: int) -> EvaluationRun:
    run = db.scalar(
        select(EvaluationRun)
        .options(selectinload(EvaluationRun.results))
        .where(EvaluationRun.id == run_id)
    )
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="evaluation run not found",
        )
    return run


def _run_metric(run: EvaluationRun, key: str) -> float | None:
    if not run.metrics:
        return None
    value = run.metrics.get(key)
    return float(value) if value is not None else None


def _metric_delta(
    baseline: float | None,
    candidate: float | None,
) -> dict[str, float | None]:
    return {
        "baseline": baseline,
        "candidate": candidate,
        "delta": (
            candidate - baseline
            if baseline is not None and candidate is not None
            else None
        ),
    }


def _result_key(result) -> tuple:
    if result.case_id is not None:
        return ("case", result.case_id)
    return (
        "snapshot",
        result.query,
        result.equipment_model_id,
        result.expected_answerable,
        tuple(sorted(result.expected_evidence_ids or [])),
    )


def _run_issue_counts(run: EvaluationRun) -> dict[str, int]:
    issue_codes = [
        "retrieval_miss",
        "ranking_error",
        "answerability_error",
        "citation_missing",
        "citation_false_positive",
        "execution_error",
    ]
    return {
        code: sum(code in evaluation_issue_codes(result) for result in run.results)
        for code in issue_codes
    }


def _run_avg_latency(run: EvaluationRun) -> float | None:
    metric_value = _run_metric(run, "avg_latency_ms")
    if metric_value is not None:
        return metric_value
    if not run.results:
        return None
    return sum(result.latency_ms for result in run.results) / len(run.results)


@router.get(
    "/runs/leaderboard",
    response_model=list[EvaluationLeaderboardItem],
)
def leaderboard(
    limit: int = Query(default=30, ge=1, le=100),
    sort_by: str = Query(default="citation_f1"),
    descending: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> list[dict]:
    runs = list(
        db.scalars(
            select(EvaluationRun)
            .options(selectinload(EvaluationRun.results))
            .order_by(EvaluationRun.id.desc())
            .limit(limit)
        ).all()
    )

    items: list[dict] = []
    for run in runs:
        issue_counts = _run_issue_counts(run)
        items.append(
            {
                "run_id": run.id,
                "status": run.status,
                "total_cases": run.total_cases,
                "parameter_snapshot": run.parameter_snapshot,
                "hit_at_k": _run_metric(run, "hit_at_k"),
                "mrr": _run_metric(run, "mrr"),
                "refusal_accuracy": _run_metric(run, "refusal_accuracy"),
                "answerability_accuracy": _run_metric(run, "answerability_accuracy"),
                "citation_f1": _run_metric(run, "citation_f1"),
                "avg_latency_ms": _run_avg_latency(run),
                "failure_count": sum(
                    bool(evaluation_issue_codes(result))
                    for result in run.results
                ),
                "issue_counts": issue_counts,
                "created_at": run.created_at,
            }
        )

    allowed = {
        "hit_at_k",
        "mrr",
        "refusal_accuracy",
        "answerability_accuracy",
        "citation_f1",
        "avg_latency_ms",
        "failure_count",
        "created_at",
    }
    if sort_by not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unsupported leaderboard sort: {sort_by}",
        )

    def sort_key(item: dict):
        value = item.get(sort_by)
        if value is None:
            return (1, 0)
        return (0, value)

    items.sort(key=sort_key, reverse=descending)
    return items


@router.post(
    "/sweeps",
    response_model=EvaluationSweepResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_sweep(
    payload: EvaluationSweepCreate,
    db: Session = Depends(get_db),
) -> dict:
    combinations = list(
        product(
            payload.top_k_values,
            payload.grounding_min_final_score_values,
            payload.grounding_min_rerank_score_values,
        )
    )
    runs: list[EvaluationRun] = []
    for top_k, final_threshold, rerank_threshold in combinations:
        run_payload = EvaluationRunCreate(
            top_k=top_k,
            case_ids=payload.case_ids,
            rough_recall_limit=payload.rough_recall_limit,
            vector_weight=payload.vector_weight,
            rerank_weight=payload.rerank_weight,
            grounding_min_final_score=final_threshold,
            grounding_min_rerank_score=rerank_threshold,
        )
        runs.append(execute_evaluation_run(db=db, payload=run_payload))

    case_count = runs[0].total_cases if runs else 0
    return {
        "combination_count": len(combinations),
        "case_count": case_count,
        "estimated_case_executions": len(combinations) * case_count,
        "runs": runs,
    }


@router.get(
    "/runs/compare",
    response_model=EvaluationRunComparisonResponse,
)
def compare_runs(
    baseline_run_id: int,
    candidate_run_id: int,
    db: Session = Depends(get_db),
) -> dict:
    if baseline_run_id == candidate_run_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="baseline and candidate runs must be different",
        )

    baseline = _get_run_or_404(db, baseline_run_id)
    candidate = _get_run_or_404(db, candidate_run_id)

    baseline_map = {_result_key(result): result for result in baseline.results}
    candidate_map = {_result_key(result): result for result in candidate.results}
    matched_keys = baseline_map.keys() & candidate_map.keys()

    samples = [
        compare_evaluation_results(
            baseline_map[key],
            candidate_map[key],
        )
        for key in matched_keys
    ]
    samples.sort(
        key=lambda item: (
            {
                "regressed": 0,
                "mixed": 1,
                "improved": 2,
                "incomparable": 3,
                "unchanged": 4,
            }.get(item["status"], 5),
            item["case_id"] or 0,
            item["query"],
        )
    )

    issue_codes = [
        "retrieval_miss",
        "ranking_error",
        "answerability_error",
        "citation_missing",
        "citation_false_positive",
        "execution_error",
    ]
    baseline_failure_counts = {
        code: sum(
            code in evaluation_issue_codes(result)
            for result in baseline.results
        )
        for code in issue_codes
    }
    candidate_failure_counts = {
        code: sum(
            code in evaluation_issue_codes(result)
            for result in candidate.results
        )
        for code in issue_codes
    }
    failure_deltas = {
        code: {
            "baseline": baseline_failure_counts[code],
            "candidate": candidate_failure_counts[code],
            "delta": (
                candidate_failure_counts[code]
                - baseline_failure_counts[code]
            ),
        }
        for code in issue_codes
    }

    baseline_latency = (
        sum(result.latency_ms for result in baseline.results)
        / len(baseline.results)
        if baseline.results
        else None
    )
    candidate_latency = (
        sum(result.latency_ms for result in candidate.results)
        / len(candidate.results)
        if candidate.results
        else None
    )

    metric_deltas = {
        key: _metric_delta(
            _run_metric(baseline, key),
            _run_metric(candidate, key),
        )
        for key in [
            "hit_at_k",
            "mrr",
            "refusal_accuracy",
            "answerability_accuracy",
            "citation_f1",
        ]
    }
    metric_deltas["avg_latency_ms"] = _metric_delta(
        baseline_latency,
        candidate_latency,
    )

    return {
        "baseline_run": baseline,
        "candidate_run": candidate,
        "metric_deltas": metric_deltas,
        "failure_deltas": failure_deltas,
        "matched_case_count": len(matched_keys),
        "baseline_only_case_count": len(
            baseline_map.keys() - candidate_map.keys()
        ),
        "candidate_only_case_count": len(
            candidate_map.keys() - baseline_map.keys()
        ),
        "regressed_count": sum(
            item["status"] == "regressed" for item in samples
        ),
        "improved_count": sum(
            item["status"] == "improved" for item in samples
        ),
        "mixed_count": sum(
            item["status"] == "mixed" for item in samples
        ),
        "unchanged_count": sum(
            item["status"] == "unchanged" for item in samples
        ),
        "incomparable_count": sum(
            item["status"] == "incomparable" for item in samples
        ),
        "samples": samples,
    }


@router.get(
    "/runs/{run_id}/threshold-errors",
    response_model=list[ThresholdErrorAnalysisResponse],
)
def threshold_errors(
    run_id: int,
    db: Session = Depends(get_db),
) -> list[dict]:
    run = _get_run_or_404(db, run_id)
    snapshot = run.parameter_snapshot or {}
    final_threshold = snapshot.get("grounding_min_final_score")
    rerank_threshold = snapshot.get("grounding_min_rerank_score")
    errors: list[dict] = []

    for result in run.results:
        if result.answerability_correct:
            continue

        trace = result.decision_trace or {}
        top_hit = result.hits[0] if result.hits else None
        top_final = trace.get(
            "top_final_score",
            top_hit.get("final_score") if top_hit else None,
        )
        top_rerank = trace.get(
            "top_rerank_score",
            top_hit.get("rerank_score") if top_hit else None,
        )
        run_final_threshold = trace.get(
            "grounding_min_final_score",
            final_threshold,
        )
        run_rerank_threshold = trace.get(
            "grounding_min_rerank_score",
            rerank_threshold,
        )

        errors.append(
            {
                "result_id": result.id,
                "case_id": result.case_id,
                "query": result.query,
                "expected_answerable": result.expected_answerable,
                "actual_grounded": result.grounded,
                "refusal_reason": result.refusal_reason,
                "top_final_score": top_final,
                "top_rerank_score": top_rerank,
                "grounding_min_final_score": run_final_threshold,
                "grounding_min_rerank_score": run_rerank_threshold,
                "final_margin": (
                    float(top_final) - float(run_final_threshold)
                    if top_final is not None and run_final_threshold is not None
                    else None
                ),
                "rerank_margin": (
                    float(top_rerank) - float(run_rerank_threshold)
                    if top_rerank is not None and run_rerank_threshold is not None
                    else None
                ),
                "decision_source": trace.get("decision_source"),
                "deepseek_answerable": trace.get("deepseek_answerable"),
                "deepseek_reason": trace.get("deepseek_reason"),
                "top_evidence": [
                    {
                        "rank": index,
                        "evidence_id": str(hit.get("evidence_id", "")),
                        "section_path": hit.get("section_path"),
                        "text": str(hit.get("text", "")),
                        "vector_score": float(hit.get("vector_score", 0.0)),
                        "rerank_score": float(hit.get("rerank_score", 0.0)),
                        "final_score": float(hit.get("final_score", 0.0)),
                    }
                    for index, hit in enumerate(result.hits[:3], start=1)
                ],
            }
        )

    return errors


@router.get(
    "/runs/{run_id}",
    response_model=EvaluationRunResponse,
)
def get_run(
    run_id: int,
    db: Session = Depends(get_db),
) -> EvaluationRun:
    return _get_run_or_404(db, run_id)


@router.post(
    "/runs",
    response_model=EvaluationRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_run(
    payload: EvaluationRunCreate,
    db: Session = Depends(get_db),
) -> EvaluationRun:
    try:
        run = execute_evaluation_run(db=db, payload=payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return get_run(run.id, db)
