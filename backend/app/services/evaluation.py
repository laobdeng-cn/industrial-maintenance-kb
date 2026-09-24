from datetime import datetime, timezone
from time import perf_counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.evaluation import (
    EvaluationCase,
    EvaluationResult,
    EvaluationRun,
)
from app.schemas.evaluation import EvaluationRunCreate
from app.schemas.search import SearchRequest
from app.services.answering import answer_question
from app.services.reranker import (
    RERANK_WEIGHT,
    ROUGH_RECALL_LIMIT,
    VECTOR_WEIGHT,
)


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _parameter_snapshot(top_k: int) -> dict:
    return {
        "snapshot_version": 1,
        "embedding_model": settings.embedding_model,
        "embedding_vector_size": settings.embedding_vector_size,
        "collection_name": settings.qdrant_collection,
        "top_k": top_k,
        "rough_recall_limit": ROUGH_RECALL_LIMIT,
        "vector_weight": VECTOR_WEIGHT,
        "rerank_weight": RERANK_WEIGHT,
        "grounding_min_final_score": settings.grounding_min_final_score,
        "grounding_min_rerank_score": settings.grounding_min_rerank_score,
        "deepseek_model": settings.deepseek_model,
        "app_env": settings.app_env,
    }


def evaluation_issue_codes(result: EvaluationResult) -> list[str]:
    issues: list[str] = []
    expected = set(result.expected_evidence_ids or [])
    hit_ids = [
        str(hit.get("evidence_id"))
        for hit in (result.hits or [])
        if hit.get("evidence_id") is not None
    ]
    citations = set(result.citation_evidence_ids or [])
    matching_ranks = [
        index
        for index, evidence_id in enumerate(hit_ids, start=1)
        if evidence_id in expected
    ]
    has_expected_hit = bool(matching_ranks)
    has_expected_citation = bool(citations & expected)
    has_extra_citation = any(
        evidence_id not in expected for evidence_id in citations
    )

    if result.error_message:
        issues.append("execution_error")
    if result.expected_answerable != result.grounded:
        issues.append("answerability_error")

    if result.expected_answerable and expected:
        if not has_expected_hit:
            issues.append("retrieval_miss")
        elif min(matching_ranks) > 1:
            issues.append("ranking_error")

        if result.grounded and has_expected_hit and not has_expected_citation:
            issues.append("citation_missing")

    if result.grounded and citations and has_extra_citation:
        issues.append("citation_false_positive")

    return issues


def _sample_citation_f1(result: EvaluationResult) -> float | None:
    precision = result.citation_precision
    recall = result.citation_recall
    if precision is None or recall is None:
        return None
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _comparison_snapshot(result: EvaluationResult) -> dict:
    return {
        "grounded": result.grounded,
        "answerability_correct": result.answerability_correct,
        "hit_at_k": result.hit_at_k,
        "first_relevant_rank": result.first_relevant_rank,
        "reciprocal_rank": result.reciprocal_rank,
        "citation_precision": result.citation_precision,
        "citation_recall": result.citation_recall,
        "latency_ms": result.latency_ms,
        "error_message": result.error_message,
    }


def compare_evaluation_results(
    baseline: EvaluationResult,
    candidate: EvaluationResult,
) -> dict:
    comparable = (
        baseline.query == candidate.query
        and baseline.equipment_model_id == candidate.equipment_model_id
        and baseline.expected_answerable == candidate.expected_answerable
        and set(baseline.expected_evidence_ids or [])
        == set(candidate.expected_evidence_ids or [])
    )

    baseline_issues = evaluation_issue_codes(baseline)
    candidate_issues = evaluation_issue_codes(candidate)
    regression_reasons: list[str] = []
    improvement_reasons: list[str] = []

    if comparable:
        if baseline.error_message is None and candidate.error_message is not None:
            regression_reasons.append("execution_error")
        elif baseline.error_message is not None and candidate.error_message is None:
            improvement_reasons.append("execution_error_recovered")

        if baseline.answerability_correct and not candidate.answerability_correct:
            regression_reasons.append("answerability_regressed")
        elif not baseline.answerability_correct and candidate.answerability_correct:
            improvement_reasons.append("answerability_improved")

        if baseline.hit_at_k is True and candidate.hit_at_k is False:
            regression_reasons.append("retrieval_hit_lost")
        elif baseline.hit_at_k is False and candidate.hit_at_k is True:
            improvement_reasons.append("retrieval_hit_recovered")

        if (
            baseline.first_relevant_rank is not None
            and candidate.first_relevant_rank is not None
        ):
            if candidate.first_relevant_rank > baseline.first_relevant_rank:
                regression_reasons.append("rank_worsened")
            elif candidate.first_relevant_rank < baseline.first_relevant_rank:
                improvement_reasons.append("rank_improved")

        baseline_f1 = _sample_citation_f1(baseline)
        candidate_f1 = _sample_citation_f1(candidate)
        if baseline_f1 is not None and candidate_f1 is not None:
            if candidate_f1 < baseline_f1 - 1e-9:
                regression_reasons.append("citation_f1_decreased")
            elif candidate_f1 > baseline_f1 + 1e-9:
                improvement_reasons.append("citation_f1_increased")

    if not comparable:
        status = "incomparable"
    elif regression_reasons and improvement_reasons:
        status = "mixed"
    elif regression_reasons:
        status = "regressed"
    elif improvement_reasons:
        status = "improved"
    else:
        status = "unchanged"

    return {
        "case_id": candidate.case_id or baseline.case_id,
        "query": candidate.query,
        "status": status,
        "comparable": comparable,
        "baseline_issue_codes": baseline_issues,
        "candidate_issue_codes": candidate_issues,
        "regression_reasons": regression_reasons,
        "improvement_reasons": improvement_reasons,
        "baseline": _comparison_snapshot(baseline),
        "candidate": _comparison_snapshot(candidate),
    }


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
        parameter_snapshot=_parameter_snapshot(payload.top_k),
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
