import re

from sqlalchemy.orm import Session

from app.core.config import settings
from app.schemas.search import (
    GroundedAnswerResponse,
    GroundedCitationResponse,
    SearchRequest,
)
from app.services.deepseek import (
    InvalidGroundedDecisionError,
    generate_grounded_decision,
)
from app.services.retrieval import retrieve_evidence
from app.services.tuning import RuntimeTuning


def _insufficient_message(query: str) -> str:
    if any("\u4e00" <= char <= "\u9fff" for char in query):
        return "现有知识库证据不足，无法可靠回答该问题。"
    return (
        "The available knowledge-base evidence is insufficient "
        "to answer this question reliably."
    )


_PARAMETER_QUERY_CONCEPTS = (
    (
        ("供电", "电压", "voltage", "supply"),
        ("supply voltage", "v dc", "voltage"),
    ),
    (
        ("数字输出", "输出电流", "电流", "current", "output"),
        ("digital outputs", "per channel", "0.5 a", "current"),
    ),
    (
        ("温度", "temperature"),
        ("operating temp", "°c", " c "),
    ),
    (
        ("以太网", "网口", "速率", "ethernet", "rj45", "mbps"),
        ("ethernet", "rj45", "mbps"),
    ),
)

_LED_QUERY_MARKERS = (
    "pwr",
    "run",
    "err",
    "link",
    "led",
    "指示灯",
    "红灯",
    "绿灯",
    "常亮",
    "闪烁",
    "熄灭",
)

_LED_TEXT_MARKERS = (
    "pwr",
    "run",
    "err",
    "link",
    "green steady",
    "green blinking",
    "red steady",
)


def _contains_any(value: str, markers: tuple[str, ...]) -> bool:
    lowered = value.casefold()
    return any(marker.casefold() in lowered for marker in markers)


def _has_structured_evidence_support(query: str, hits) -> bool:
    """Detect conservative, explicit structured support in the top evidence.

    This signal never answers a question by itself. It records that a low
    lexical rerank score must not veto the semantic DeepSeek judge, especially
    for Chinese questions against English tables or LED/status labels.
    """
    if not hits:
        return False

    top_hit = hits[0]
    query_lower = query.casefold()
    text_lower = (top_hit.text or "").casefold()
    section_lower = (top_hit.section_path or "").casefold()

    if top_hit.block_type == "table":
        for query_markers, evidence_markers in _PARAMETER_QUERY_CONCEPTS:
            if _contains_any(query_lower, query_markers) and _contains_any(
                text_lower,
                evidence_markers,
            ):
                if re.search(r"\d", text_lower):
                    return True

    if (
        _contains_any(query_lower, _LED_QUERY_MARKERS)
        and (
            "led status" in section_lower
            or _contains_any(text_lower, _LED_TEXT_MARKERS)
        )
    ):
        symbols = re.findall(r"\b(?:pwr|run|err|link)\b", query_lower)
        if symbols:
            return all(symbol in text_lower for symbol in symbols)

        state_pairs = (
            ("红灯", "red steady"),
            ("常亮", "steady"),
            ("闪烁", "blinking"),
            ("熄灭", "off"),
        )
        matched_state = [
            evidence_marker
            for query_marker, evidence_marker in state_pairs
            if query_marker in query_lower
        ]
        if matched_state:
            return all(marker in text_lower for marker in matched_state)

        return "led status" in section_lower

    return False


def _citation(index: int, hit) -> GroundedCitationResponse:
    return GroundedCitationResponse(
        index=index,
        evidence_id=hit.evidence_id,
        document_id=hit.document_id,
        block_id=hit.block_id,
        title=hit.title,
        version=hit.version,
        section_path=hit.section_path,
        page_start=hit.page_start,
        page_end=hit.page_end,
        asset_id=hit.asset_id,
        text=hit.text,
    )


def _response(
    *,
    payload: SearchRequest,
    retrieval,
    tuning: RuntimeTuning,
    grounded: bool,
    answer: str,
    refusal_reason: str | None,
    model: str | None,
    top_final_score: float | None,
    top_rerank_score: float | None,
    citations: list[GroundedCitationResponse],
    decision_source: str,
    deepseek_answerable: bool | None,
    deepseek_reason: str | None,
    structured_evidence_support: bool,
    rerank_gate_bypassed: bool,
) -> GroundedAnswerResponse:
    return GroundedAnswerResponse(
        query=payload.query,
        equipment_model_id=payload.equipment_model_id,
        grounded=grounded,
        answer=answer,
        refusal_reason=refusal_reason,
        model=model,
        grounding_threshold=tuning.grounding_min_final_score,
        grounding_rerank_threshold=tuning.grounding_min_rerank_score,
        top_final_score=top_final_score,
        top_rerank_score=top_rerank_score,
        decision_source=decision_source,
        deepseek_answerable=deepseek_answerable,
        deepseek_reason=deepseek_reason,
        structured_evidence_support=structured_evidence_support,
        rerank_gate_bypassed=rerank_gate_bypassed,
        embedding_model=retrieval.embedding_model,
        collection_name=retrieval.collection_name,
        rough_recall_limit=retrieval.rough_recall_limit,
        citations=citations,
        hits=retrieval.hits,
    )


def answer_question(
    payload: SearchRequest,
    db: Session,
    tuning: RuntimeTuning | None = None,
) -> GroundedAnswerResponse:
    tuning = tuning or RuntimeTuning.defaults()
    retrieval = retrieve_evidence(payload=payload, db=db, tuning=tuning)

    top_final_score = retrieval.hits[0].final_score if retrieval.hits else None
    top_rerank_score = retrieval.hits[0].rerank_score if retrieval.hits else None

    # Stage 1: final_score is the primary coarse gate. rerank_score remains a
    # soft diagnostic signal instead of a hard AND condition because bilingual
    # structured evidence can be semantically correct while lexically weak.
    if (
        not retrieval.hits
        or top_final_score is None
        or top_final_score < tuning.grounding_min_final_score
    ):
        return _response(
            payload=payload,
            retrieval=retrieval,
            tuning=tuning,
            grounded=False,
            answer=_insufficient_message(payload.query),
            refusal_reason="insufficient_evidence",
            model=None,
            top_final_score=top_final_score,
            top_rerank_score=top_rerank_score,
            citations=[],
            decision_source="threshold_gate",
            deepseek_answerable=None,
            deepseek_reason=None,
            structured_evidence_support=False,
            rerank_gate_bypassed=False,
        )

    structured_support = _has_structured_evidence_support(
        payload.query,
        retrieval.hits,
    )
    rerank_gate_bypassed = bool(
        top_rerank_score is not None
        and top_rerank_score < tuning.grounding_min_rerank_score
    )

    # Stage 2: every final_score-qualified candidate reaches the semantic judge.
    # Structured support is a debug/explainability signal, not an auto-answer.
    try:
        decision = generate_grounded_decision(query=payload.query, hits=retrieval.hits)
    except InvalidGroundedDecisionError:
        return _response(
            payload=payload,
            retrieval=retrieval,
            tuning=tuning,
            grounded=False,
            answer=_insufficient_message(payload.query),
            refusal_reason="invalid_grounded_decision",
            model=settings.deepseek_model,
            top_final_score=top_final_score,
            top_rerank_score=top_rerank_score,
            citations=[],
            decision_source="refused",
            deepseek_answerable=None,
            deepseek_reason="invalid_grounded_decision",
            structured_evidence_support=structured_support,
            rerank_gate_bypassed=rerank_gate_bypassed,
        )

    if not decision.answerable:
        return _response(
            payload=payload,
            retrieval=retrieval,
            tuning=tuning,
            grounded=False,
            answer=_insufficient_message(payload.query),
            refusal_reason="insufficient_evidence",
            model=settings.deepseek_model,
            top_final_score=top_final_score,
            top_rerank_score=top_rerank_score,
            citations=[],
            decision_source="refused",
            deepseek_answerable=False,
            deepseek_reason=decision.reason,
            structured_evidence_support=structured_support,
            rerank_gate_bypassed=rerank_gate_bypassed,
        )

    citations = [
        _citation(index, retrieval.hits[index - 1])
        for index in decision.citations
    ]

    return _response(
        payload=payload,
        retrieval=retrieval,
        tuning=tuning,
        grounded=True,
        answer=decision.answer,
        refusal_reason=None,
        model=settings.deepseek_model,
        top_final_score=top_final_score,
        top_rerank_score=top_rerank_score,
        citations=citations,
        decision_source=(
            "structured_evidence_override"
            if rerank_gate_bypassed and structured_support
            else "deepseek_judge"
        ),
        deepseek_answerable=True,
        deepseek_reason=decision.reason,
        structured_evidence_support=structured_support,
        rerank_gate_bypassed=rerank_gate_bypassed,
    )
