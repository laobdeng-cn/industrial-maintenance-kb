from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.deps import get_db
from app.models.equipment import EquipmentModel
from app.models.evaluation import EvaluationCase, EvaluationRun
from app.schemas.evaluation import (
    EvaluationCaseCreate,
    EvaluationCaseResponse,
    EvaluationCaseUpdate,
    EvaluationRunComparisonResponse,
    EvaluationRunCreate,
    EvaluationRunResponse,
    EvaluationRunSummaryResponse,
)
from app.services.evaluation import (
    compare_evaluation_results,
    evaluation_issue_codes,
    execute_evaluation_run,
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

    case = EvaluationCase(**payload.model_dump())
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

    for key, value in changes.items():
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
