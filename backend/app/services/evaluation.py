from datetime import datetime, timezone
from time import perf_counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.evaluation import (
    EvaluationCase,
    EvaluationResult,
    EvaluationRun,
)
from app.schemas.evaluation import EvaluationRunCreate
from app.schemas.search import SearchRequest
from app.services.answering import answer_question


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def execute_evaluation_run(
    *,
    db: Session,
    payload: EvaluationRunCreate,
) -> EvaluationRun:
    statement = select(EvaluationCase).order_by(EvaluationCase.id)

    if payload.case_ids:
        unique_ids = list(dict.fromkeys(payload.case_ids))
        statement = statement.where(EvaluationCase.id.in_(unique_ids))

    cases = list(db.scalars(statement).all())
    if len(cases) > 50:
        raise ValueError("a single evaluation run is limited to 50 cases")

    run = EvaluationRun(
        status="running",
        top_k=payload.top_k,
        total_cases=len(cases),
        completed_cases=0,
    )
    db.add(run)
    db.flush()

    hit_values: list[float] = []
    rr_values: list[float] = []
    citation_precisions: list[float] = []
    citation_recalls: list[float] = []
    answerability_values: list[float] = []
    refusal_values: list[float] = []
    error_count = 0

    for case in cases:
        started = perf_counter()
        expected_ids = list(case.expected_evidence_ids or [])
        expected_set = set(expected_ids)

        try:
            response = answer_question(
                payload=SearchRequest(
                    query=case.query,
                    equipment_model_id=case.equipment_model_id,
                    limit=payload.top_k,
                ),
                db=db,
            )

            hit_ids = [hit.evidence_id for hit in response.hits]
            citation_ids = [
                citation.evidence_id
                for citation in response.citations
            ]

            hit_at_k: bool | None = None
            first_rank: int | None = None
            reciprocal_rank: float | None = None
            citation_precision: float | None = None
            citation_recall: float | None = None

            if expected_set:
                matching_ranks = [
                    index
                    for index, evidence_id in enumerate(hit_ids, start=1)
                    if evidence_id in expected_set
                ]
                first_rank = min(matching_ranks) if matching_ranks else None
                hit_at_k = first_rank is not None
                reciprocal_rank = (
                    1.0 / first_rank
                    if first_rank is not None
                    else 0.0
                )

                cited_set = set(citation_ids)
                overlap = len(cited_set & expected_set)
                citation_precision = (
                    overlap / len(cited_set)
                    if cited_set
                    else 0.0
                )
                citation_recall = overlap / len(expected_set)

                hit_values.append(1.0 if hit_at_k else 0.0)
                rr_values.append(reciprocal_rank)
                citation_precisions.append(citation_precision)
                citation_recalls.append(citation_recall)

            answerability_correct = (
                response.grounded == case.expected_answerable
            )
            answerability_values.append(
                1.0 if answerability_correct else 0.0
            )

            if not case.expected_answerable:
                refusal_values.append(
                    1.0 if not response.grounded else 0.0
                )

            result = EvaluationResult(
                run_id=run.id,
                case_id=case.id,
                query=case.query,
                equipment_model_id=case.equipment_model_id,
                expected_evidence_ids=expected_ids,
                expected_answerable=case.expected_answerable,
                grounded=response.grounded,
                refusal_reason=response.refusal_reason,
                answer=response.answer,
                hits=[
                    hit.model_dump(mode="json")
                    for hit in response.hits
                ],
                citation_evidence_ids=citation_ids,
                hit_at_k=hit_at_k,
                first_relevant_rank=first_rank,
                reciprocal_rank=reciprocal_rank,
                citation_precision=citation_precision,
                citation_recall=citation_recall,
                answerability_correct=answerability_correct,
                latency_ms=round((perf_counter() - started) * 1000),
                error_message=None,
            )
        except Exception as exc:
            error_count += 1
            answerability_values.append(0.0)
            if not case.expected_answerable:
                refusal_values.append(0.0)

            result = EvaluationResult(
                run_id=run.id,
                case_id=case.id,
                query=case.query,
                equipment_model_id=case.equipment_model_id,
                expected_evidence_ids=expected_ids,
                expected_answerable=case.expected_answerable,
                grounded=False,
                refusal_reason="evaluation_error",
                answer="",
                hits=[],
                citation_evidence_ids=[],
                hit_at_k=False if expected_set else None,
                first_relevant_rank=None,
                reciprocal_rank=0.0 if expected_set else None,
                citation_precision=0.0 if expected_set else None,
                citation_recall=0.0 if expected_set else None,
                answerability_correct=False,
                latency_ms=round((perf_counter() - started) * 1000),
                error_message=f"{type(exc).__name__}: {exc}",
            )

            if expected_set:
                hit_values.append(0.0)
                rr_values.append(0.0)
                citation_precisions.append(0.0)
                citation_recalls.append(0.0)

        db.add(result)
        run.completed_cases += 1

    precision = _mean(citation_precisions)
    recall = _mean(citation_recalls)
    citation_f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None
        and recall is not None
        and precision + recall > 0
        else 0.0
        if precision is not None and recall is not None
        else None
    )

    run.metrics = {
        "hit_at_k": _mean(hit_values),
        "mrr": _mean(rr_values),
        "refusal_accuracy": _mean(refusal_values),
        "answerability_accuracy": _mean(answerability_values),
        "citation_precision": precision,
        "citation_recall": recall,
        "citation_f1": citation_f1,
        "retrieval_case_count": len(hit_values),
        "unanswerable_case_count": len(refusal_values),
        "error_count": error_count,
    }
    run.status = (
        "completed_with_errors"
        if error_count
        else "completed"
    )
    run.completed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(run)
    return run
