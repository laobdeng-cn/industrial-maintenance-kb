from __future__ import annotations

from collections import Counter
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.evaluation import EvaluationCase, EvaluationResult
from app.models.feedback import QueryLog
from app.services.evaluation import evaluation_issue_codes
from app.services.feedback_analytics import build_query_clusters


ROOT_CAUSES = (
    "knowledge_gap",
    "retrieval_gap",
    "ranking_problem",
    "answerability_gate",
    "citation_problem",
    "prompt_generation",
)


def _evidence_ids(items: list[dict] | None) -> list[str]:
    return [
        str(item.get("evidence_id"))
        for item in (items or [])
        if item.get("evidence_id")
    ]


def _score_values(logs: list[QueryLog], key: str) -> list[float]:
    values: list[float] = []
    for log in logs:
        for hit in log.hits or []:
            raw = hit.get(key)
            if raw is None:
                continue
            try:
                values.append(float(raw))
            except (TypeError, ValueError):
                continue
    return values


def _avg_nullable(values: list[float]) -> float | None:
    if not values:
        return None
    return round(mean(values), 4)


def _regression_signals(
    db: Session,
    logs: list[QueryLog],
) -> dict[str, int]:
    checked = 0
    improved = 0
    stable_healthy = 0
    regressed = 0

    for log in logs:
        review = log.review_item
        if (
            review is None
            or review.promoted_case_id is None
            or review.baseline_run_id is None
            or review.last_regression_run_id is None
        ):
            continue

        baseline = db.scalar(
            select(EvaluationResult).where(
                EvaluationResult.run_id == review.baseline_run_id,
                EvaluationResult.case_id == review.promoted_case_id,
            )
        )
        candidate = db.scalar(
            select(EvaluationResult).where(
                EvaluationResult.run_id == review.last_regression_run_id,
                EvaluationResult.case_id == review.promoted_case_id,
            )
        )
        if baseline is None or candidate is None:
            continue

        checked += 1
        baseline_issues = set(evaluation_issue_codes(baseline))
        candidate_issues = set(evaluation_issue_codes(candidate))

        if len(candidate_issues) < len(baseline_issues):
            improved += 1
        elif not baseline_issues and not candidate_issues:
            stable_healthy += 1
        elif len(candidate_issues) > len(baseline_issues):
            regressed += 1

    return {
        "checked": checked,
        "improved": improved,
        "stable_healthy": stable_healthy,
        "regressed": regressed,
    }


def _review_signals(logs: list[QueryLog]) -> dict[str, int]:
    accepted = 0
    ignored = 0
    pending = 0
    reviewer_notes = 0
    feedback_details = 0

    for log in logs:
        review = log.review_item
        if review is not None:
            accepted += int(review.status == "accepted")
            ignored += int(review.status == "ignored")
            pending += int(review.status == "pending")
            reviewer_notes += int(bool((review.reviewer_note or "").strip()))

        feedback = log.feedback
        if feedback is not None:
            feedback_details += int(
                bool((feedback.reason or "").strip())
                or bool((feedback.comment or "").strip())
            )

    return {
        "accepted": accepted,
        "ignored": ignored,
        "pending": pending,
        "reviewer_notes": reviewer_notes,
        "feedback_details": feedback_details,
    }


def _diagnosis_status(
    *,
    root_cause: str,
    confidence: float,
    generation_issue: int,
    size: int,
    review_signals: dict[str, int],
    regression_signals: dict[str, int],
) -> str:
    if regression_signals["improved"] > 0 and confidence >= 0.65:
        return "resolved_by_regression"

    if root_cause == "prompt_generation":
        corroborated = (
            generation_issue >= 2
            or review_signals["feedback_details"] >= 1
            or review_signals["reviewer_notes"] >= 1
        )
        if (
            generation_issue <= 1
            and size <= 1
            and not corroborated
        ):
            return "needs_human_validation"
        if confidence >= 0.78 and corroborated:
            return "confirmed"
        if confidence < 0.58:
            return "needs_human_validation"
        return "probable"

    if confidence >= 0.8:
        return "confirmed"
    if confidence < 0.58:
        return "needs_human_validation"
    return "probable"


def _recommendations(
    root_cause: str,
    *,
    has_ground_truth: bool,
    diagnosis_status: str,
) -> list[dict]:
    common_regression = {
        "action": "regression",
        "title": "回归验证修复效果",
        "detail": (
            "在当前 Cluster 的 Golden Case 上建立/复用 Baseline，修复后运行 Candidate，"
            "确认没有新增 Regression。"
        ),
    }

    mapping: dict[str, list[dict]] = {
        "knowledge_gap": [
            {
                "action": "knowledge",
                "title": "补齐知识覆盖",
                "detail": (
                    "确认该问题是否属于产品支持范围；若属于，补充并发布对应设备手册、FAQ、"
                    "故障码或参数说明，再重新解析与索引。"
                ),
            },
            {
                "action": "golden_set",
                "title": "建立可验证 Ground Truth",
                "detail": (
                    "新增或修订 Golden Case，标注核心 Expected Evidence 与允许引用的 Evidence，"
                    "避免把“没有资料”和“检索失败”混在一起。"
                ),
            },
            common_regression,
        ],
        "retrieval_gap": [
            {
                "action": "retrieval",
                "title": "排查召回链路",
                "detail": (
                    "检查设备型号绑定、published 过滤、Qdrant payload 与 collection；"
                    "同时确认 query rewrite / embedding 是否把正确 Evidence 召回到 Top-20。"
                ),
            },
            {
                "action": "indexing",
                "title": "重建受影响文档索引",
                "detail": (
                    "对相关文档重新解析、Embedding 与 Qdrant upsert，并核对 Evidence ID 是否稳定。"
                ),
            },
            common_regression,
        ],
        "ranking_problem": [
            {
                "action": "rerank",
                "title": "调优二阶段排序",
                "detail": (
                    "Expected Evidence 已被粗召回但排名靠后；检查 lexical/intent/section 规则，"
                    "并用 Phase C.4 Sweep 调整 Vector/Rerank 权重。"
                ),
            },
            {
                "action": "debug",
                "title": "对比 Expected Evidence 的 rank",
                "detail": (
                    "保留 Top-20 调试字段，定位正确 Evidence 在 vector_score、rerank_score、"
                    "final_score 哪一阶段被压低。"
                ),
            },
            common_regression,
        ],
        "answerability_gate": [
            {
                "action": "gate",
                "title": "校准 Answerability Gate",
                "detail": (
                    "检查 grounding final/rerank 阈值与 structured evidence override，"
                    "避免“已有明确 Evidence 但被阈值拒答”或“弱证据误放行”。"
                ),
            },
            {
                "action": "sweep",
                "title": "使用 Golden Set 做阈值 Sweep",
                "detail": (
                    "围绕 Final/Rerank Gate 做参数实验，优先保证 Answerability Accuracy，"
                    "再观察 Citation F1 与拒答准确率。"
                ),
            },
            common_regression,
        ],
        "citation_problem": [
            {
                "action": "citation",
                "title": "修正 Citation 选择与映射",
                "detail": (
                    "确认最终答案引用的是 Expected/Allowed Evidence，并核对 [n] → Evidence ID → "
                    "document/block/page 映射。"
                ),
            },
            {
                "action": "generation",
                "title": "约束回答必须逐条落证据",
                "detail": (
                    "生成阶段只允许使用已选 Evidence，缺少直接支撑时删除对应结论或拒答。"
                ),
            },
            common_regression,
        ],
        "prompt_generation": [
            {
                "action": "review",
                "title": "先确认是否真是生成层问题",
                "detail": (
                    "查看用户 comment、Reviewer Note 与相似 Trace。若只有单次 unhelpful 且"
                    "Expected Evidence / Citation 均正确，不应直接据此修改 Prompt。"
                ),
            },
            {
                "action": "prompt",
                "title": "在证据充分时再调整 Grounded Answer Prompt",
                "detail": (
                    "只有当重复负反馈、人工审查或回归结果能够复现答案遗漏/表达问题时，"
                    "再优化答案结构、完整度、术语一致性与问题意图覆盖。"
                ),
            },
            common_regression,
        ],
    }

    items = list(mapping[root_cause])
    if root_cause == "prompt_generation" and diagnosis_status == "needs_human_validation":
        items.insert(
            0,
            {
                "action": "validation",
                "title": "暂缓 Prompt 调参",
                "detail": (
                    "当前证据只支持“生成层候选根因”，尚不足以形成高置信结论。"
                    "先完成一次人工复核或等待同类问题重复出现，再进入 Prompt 优化。"
                ),
            },
        )
    if not has_ground_truth and root_cause not in {"knowledge_gap", "retrieval_gap"}:
        items.insert(
            1,
            {
                "action": "golden_set",
                "title": "补充 Golden Evidence",
                "detail": "当前 Cluster 缺少明确 Expected Evidence，建议先完成标注再做定向调参。",
            },
        )
    return items


def _diagnose_cluster(
    db: Session,
    cluster: dict,
) -> dict:
    query_log_ids = [member["query_log_id"] for member in cluster["members"]]
    logs = list(
        db.scalars(
            select(QueryLog)
            .options(selectinload(QueryLog.feedback), selectinload(QueryLog.review_item))
            .where(QueryLog.id.in_(query_log_ids))
            .order_by(QueryLog.id.asc())
        ).all()
    )

    case_ids = cluster["promoted_case_ids"]
    cases = (
        list(
            db.scalars(
                select(EvaluationCase).where(EvaluationCase.id.in_(case_ids))
            ).all()
        )
        if case_ids
        else []
    )

    expected_ids = {
        evidence_id
        for case in cases
        for evidence_id in (case.expected_evidence_ids or [])
    }
    allowed_ids = {
        evidence_id
        for case in cases
        for evidence_id in (case.allowed_citation_evidence_ids or [])
    }
    expected_answerable_values = [case.expected_answerable for case in cases]

    no_hit_count = 0
    no_citation_count = 0
    refused_count = 0
    grounded_count = 0
    unhelpful_count = 0
    expected_retrieval_miss = 0
    expected_ranked_below_top1 = 0
    expected_citation_miss = 0
    gate_miss = 0
    generation_issue = 0

    final_scores: list[float] = []
    rerank_scores: list[float] = []
    best_vector_scores: list[float] = []

    for log in logs:
        hit_ids = _evidence_ids(log.hits)
        citation_ids = _evidence_ids(log.citations)
        hit_set = set(hit_ids)
        citation_set = set(citation_ids)

        grounded_count += int(log.grounded)
        refused_count += int(not log.grounded)
        unhelpful_count += int(
            log.feedback is not None and log.feedback.rating == "unhelpful"
        )
        no_hit_count += int(len(hit_ids) == 0)
        no_citation_count += int(len(citation_ids) == 0)

        if log.top_final_score is not None:
            final_scores.append(float(log.top_final_score))
        if log.top_rerank_score is not None:
            rerank_scores.append(float(log.top_rerank_score))

        vector_candidates = []
        for hit in log.hits or []:
            try:
                vector_candidates.append(float(hit.get("vector_score", 0.0)))
            except (TypeError, ValueError):
                continue
        if vector_candidates:
            best_vector_scores.append(max(vector_candidates))

        if expected_ids:
            expected_in_hits = expected_ids & hit_set
            expected_in_citations = expected_ids & citation_set
            if not expected_in_hits:
                expected_retrieval_miss += 1
            else:
                if not hit_ids or hit_ids[0] not in expected_ids:
                    expected_ranked_below_top1 += 1
                if log.grounded and not expected_in_citations:
                    expected_citation_miss += 1
                if not log.grounded:
                    gate_miss += 1

        if (
            log.grounded
            and log.feedback is not None
            and log.feedback.rating == "unhelpful"
            and (
                not expected_ids
                or bool(expected_ids & citation_set)
                or bool(allowed_ids & citation_set)
            )
        ):
            generation_issue += 1

        if (
            not log.grounded
            and log.top_final_score is not None
            and float(log.top_final_score) >= settings.grounding_min_final_score * 0.95
            and len(hit_ids) > 0
        ):
            gate_miss += 1

    avg_final = _avg_nullable(final_scores)
    avg_rerank = _avg_nullable(rerank_scores)
    avg_best_vector = _avg_nullable(best_vector_scores)
    size = max(1, len(logs))
    review_signals = _review_signals(logs)
    regression_signals = _regression_signals(db, logs)

    expected_hit_coverage: float | None = None
    if expected_ids and logs:
        expected_hit_coverage = round(
            max(0.0, 1.0 - expected_retrieval_miss / len(logs)),
            4,
        )

    knowledge_gap_score = 0.0
    if not cases or not expected_ids:
        knowledge_gap_score += 25.0
    if refused_count / size >= 0.5:
        knowledge_gap_score += 20.0
    if no_citation_count / size >= 0.5:
        knowledge_gap_score += 15.0
    if avg_rerank is None or avg_rerank < settings.grounding_min_rerank_score:
        knowledge_gap_score += 15.0
    if avg_best_vector is None or avg_best_vector < 0.35:
        knowledge_gap_score += 15.0
    if cluster["size"] > 1:
        knowledge_gap_score += min(10.0, (cluster["size"] - 1) * 3.0)
    if unhelpful_count > 0:
        knowledge_gap_score += min(10.0, unhelpful_count * 5.0)
    knowledge_gap_score = round(min(100.0, knowledge_gap_score), 1)

    root_cause = "prompt_generation"
    confidence = 0.62

    if expected_ids:
        if expected_retrieval_miss > 0:
            root_cause = "retrieval_gap"
            confidence = min(0.97, 0.72 + expected_retrieval_miss / size * 0.2)
        elif gate_miss > 0:
            root_cause = "answerability_gate"
            confidence = min(0.95, 0.72 + gate_miss / size * 0.18)
        elif expected_ranked_below_top1 > 0:
            root_cause = "ranking_problem"
            confidence = min(0.94, 0.7 + expected_ranked_below_top1 / size * 0.18)
        elif expected_citation_miss > 0:
            root_cause = "citation_problem"
            confidence = min(0.94, 0.7 + expected_citation_miss / size * 0.18)
        elif generation_issue > 0:
            root_cause = "prompt_generation"
            # A single thumbs-down is only a weak generation signal. Confidence
            # grows with recurrence and independent human/regression evidence.
            confidence = 0.42 + 0.12 * min(1.0, generation_issue / size)
            if generation_issue >= 2:
                confidence += min(0.18, 0.07 * (generation_issue - 1))
            if review_signals["feedback_details"] > 0:
                confidence += 0.06
            if review_signals["accepted"] > 0:
                confidence += 0.02
            if review_signals["reviewer_notes"] > 0:
                confidence += 0.06
            if review_signals["ignored"] > 0:
                confidence -= 0.18
            if review_signals["pending"] > 0:
                confidence -= 0.03
            if regression_signals["improved"] > 0:
                confidence += 0.08
            if regression_signals["stable_healthy"] > 0:
                confidence -= 0.06
            if regression_signals["regressed"] > 0:
                confidence -= 0.04
            if size <= 1 and generation_issue <= 1 and regression_signals["improved"] == 0:
                confidence = min(confidence, 0.62)
            confidence = max(0.35, min(0.9, confidence))
        elif knowledge_gap_score >= 70:
            root_cause = "knowledge_gap"
            confidence = 0.68
    else:
        likely_intentionally_unanswerable = (
            bool(expected_answerable_values)
            and all(value is False for value in expected_answerable_values)
        )
        if no_hit_count == size or (avg_best_vector is not None and avg_best_vector < 0.2):
            root_cause = "retrieval_gap"
            confidence = 0.82
        elif gate_miss > 0:
            root_cause = "answerability_gate"
            confidence = min(0.9, 0.68 + gate_miss / size * 0.16)
        elif knowledge_gap_score >= 55 and (
            refused_count > 0 or unhelpful_count > 0
        ):
            root_cause = "knowledge_gap"
            confidence = 0.78 if not likely_intentionally_unanswerable else 0.66
        elif grounded_count > 0 and no_citation_count > 0:
            root_cause = "citation_problem"
            confidence = 0.7
        else:
            root_cause = "prompt_generation"
            confidence = 0.5
            if review_signals["feedback_details"] > 0:
                confidence += 0.05
            if review_signals["reviewer_notes"] > 0:
                confidence += 0.05
            if review_signals["ignored"] > 0:
                confidence -= 0.15
            confidence = max(0.35, min(0.68, confidence))

    if expected_ids:
        coverage_status = (
            "covered"
            if expected_retrieval_miss == 0
            else "partial"
            if expected_retrieval_miss < size
            else "missing"
        )
    elif no_hit_count == size:
        coverage_status = "missing"
    elif knowledge_gap_score >= 55:
        coverage_status = "partial"
    else:
        coverage_status = "unknown"

    signals: list[str] = []
    if unhelpful_count:
        signals.append(f"{unhelpful_count}/{size} 条负反馈")
    if refused_count:
        signals.append(f"{refused_count}/{size} 次拒答")
    if expected_ids:
        signals.append(f"Expected Evidence {len(expected_ids)} 条")
        signals.append(
            f"Expected Hit Coverage {(expected_hit_coverage or 0.0) * 100:.0f}%"
        )
    else:
        signals.append("缺少明确 Expected Evidence")
    if expected_retrieval_miss:
        signals.append(f"{expected_retrieval_miss} 次未召回 Expected Evidence")
    if expected_ranked_below_top1:
        signals.append(f"{expected_ranked_below_top1} 次 Expected Evidence 非 Top-1")
    if expected_citation_miss:
        signals.append(f"{expected_citation_miss} 次 Grounded 但漏引 Expected Evidence")
    if gate_miss:
        signals.append(f"{gate_miss} 次疑似 Gate 误判")
    if generation_issue:
        signals.append(f"{generation_issue} 次证据充分但回答仍获负反馈")
    if review_signals["accepted"]:
        signals.append(f"{review_signals['accepted']} 条 Review accepted")
    if review_signals["pending"]:
        signals.append(f"{review_signals['pending']} 条 Review 待人工确认")
    if review_signals["ignored"]:
        signals.append(f"{review_signals['ignored']} 条 Review ignored")
    if review_signals["feedback_details"]:
        signals.append(f"{review_signals['feedback_details']} 条反馈带 reason/comment")
    if review_signals["reviewer_notes"]:
        signals.append(f"{review_signals['reviewer_notes']} 条 Review 带人工备注")
    if regression_signals["improved"]:
        signals.append(f"{regression_signals['improved']} 条回归已改善")
    if regression_signals["stable_healthy"]:
        signals.append(
            f"{regression_signals['stable_healthy']} 条回归前后均 healthy，未复现自动评测异常"
        )
    if regression_signals["regressed"]:
        signals.append(f"{regression_signals['regressed']} 条回归出现退化")
    if avg_final is not None:
        signals.append(f"avg final {avg_final:.4f}")
    if avg_rerank is not None:
        signals.append(f"avg rerank {avg_rerank:.4f}")

    summary_map = {
        "knowledge_gap": "当前知识库对该问题的直接证据覆盖不足，优先判断是否需要补充并发布新的知识材料。",
        "retrieval_gap": "已有 Ground Truth 或候选证据，但召回链路没有稳定把正确 Evidence 带入候选集。",
        "ranking_problem": "正确 Evidence 已被召回，但二阶段排序没有稳定把它提升到前列。",
        "answerability_gate": "检索结果具备一定支持，但 Answerability Gate 的放行/拒答行为与 Ground Truth 不一致。",
        "citation_problem": "检索与回答基本可用，但 Citation 选择或 Evidence 映射没有对齐 Ground Truth。",
        "prompt_generation": "Evidence 已基本到位，生成层是候选根因；若仅有单次负反馈，应先人工复核，避免把偶发反馈直接解释为 Prompt 缺陷。",
    }

    diagnosis_status = _diagnosis_status(
        root_cause=root_cause,
        confidence=confidence,
        generation_issue=generation_issue,
        size=size,
        review_signals=review_signals,
        regression_signals=regression_signals,
    )

    return {
        "cluster_id": cluster["cluster_id"],
        "cluster_key": cluster["cluster_key"],
        "representative_query": cluster["representative_query"],
        "root_cause": root_cause,
        "confidence": round(confidence, 3),
        "diagnosis_status": diagnosis_status,
        "knowledge_gap_score": knowledge_gap_score,
        "coverage_status": coverage_status,
        "summary": summary_map[root_cause],
        "signals": signals,
        "recommendations": _recommendations(
            root_cause,
            has_ground_truth=bool(expected_ids),
            diagnosis_status=diagnosis_status,
        ),
        "affected_query_log_ids": query_log_ids,
        "promoted_case_ids": case_ids,
        "expected_evidence_count": len(expected_ids),
        "expected_hit_coverage": expected_hit_coverage,
        "average_top_final_score": avg_final,
        "average_top_rerank_score": avg_rerank,
        "review_signal_counts": review_signals,
        "regression_signal_counts": regression_signals,
        "priority_score": cluster["priority_score"],
        "priority_level": cluster["priority_level"],
    }


def build_cluster_diagnostics(
    db: Session,
    *,
    days: int,
    limit: int,
    similarity_threshold: float,
    only_problematic: bool,
) -> dict:
    cluster_payload = build_query_clusters(
        db,
        days=days,
        limit=limit,
        similarity_threshold=similarity_threshold,
        only_problematic=only_problematic,
    )

    diagnostics = [
        _diagnose_cluster(db, cluster)
        for cluster in cluster_payload["clusters"]
    ]
    diagnostics.sort(
        key=lambda item: (
            item["priority_score"],
            item["knowledge_gap_score"],
            item["confidence"],
        ),
        reverse=True,
    )

    root_cause_counts = Counter(item["root_cause"] for item in diagnostics)
    coverage_counts = Counter(item["coverage_status"] for item in diagnostics)

    return {
        "window_days": days,
        "similarity_threshold": cluster_payload["similarity_threshold"],
        "only_problematic": cluster_payload["only_problematic"],
        "sample_count": cluster_payload["sample_count"],
        "cluster_count": cluster_payload["cluster_count"],
        "clusters": cluster_payload["clusters"],
        "knowledge_gap_count": sum(
            1 for item in diagnostics if item["root_cause"] == "knowledge_gap"
        ),
        "root_cause_counts": {
            cause: root_cause_counts.get(cause, 0)
            for cause in ROOT_CAUSES
        },
        "coverage_counts": {
            key: coverage_counts.get(key, 0)
            for key in ("covered", "partial", "missing", "unknown")
        },
        "diagnostics": diagnostics,
    }
