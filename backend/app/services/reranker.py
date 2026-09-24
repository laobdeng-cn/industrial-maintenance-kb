import re
from dataclasses import dataclass


ROUGH_RECALL_LIMIT = 20
VECTOR_WEIGHT = 0.65
RERANK_WEIGHT = 0.35

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "be",
    "do",
    "for",
    "from",
    "how",
    "i",
    "if",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "should",
    "the",
    "to",
    "what",
    "when",
    "where",
    "which",
    "with",
    "would",
    "什么",
    "应该",
    "如何",
    "怎么",
}

_SYNONYM_GROUPS = (
    {
        "check",
        "verify",
        "inspect",
        "confirm",
        "test",
        "measure",
        "review",
        "检查",
        "排查",
        "确认",
        "验证",
        "测试",
    },
    {
        "power",
        "pwr",
        "voltage",
        "supply",
        "electric",
        "电源",
        "供电",
        "电压",
    },
    {
        "off",
        "down",
        "lost",
        "loss",
        "unavailable",
        "断电",
        "掉电",
        "没电",
        "无电",
        "关闭",
    },
    {
        "error",
        "err",
        "fault",
        "alarm",
        "故障",
        "错误",
        "报警",
    },
    {
        "network",
        "link",
        "ethernet",
        "connection",
        "网络",
        "链路",
        "连接",
    },
)

_SYNONYM_LOOKUP = {
    token: group
    for group in _SYNONYM_GROUPS
    for token in group
}

_TROUBLESHOOT_QUERY_MARKERS = (
    "check",
    "verify",
    "inspect",
    "troubleshoot",
    "what should",
    "how",
    "why",
    "fault",
    "error",
    "检查",
    "排查",
    "怎么办",
    "如何",
    "故障",
    "错误",
)

_TROUBLESHOOT_SECTION_MARKERS = (
    "troubleshoot",
    "procedure",
    "diagnostic",
    "fault",
    "error",
    "故障",
    "排查",
    "诊断",
    "处理",
)

_PROCEDURAL_TEXT_MARKERS = (
    "verify",
    "check",
    "confirm",
    "inspect",
    "measure",
    "replace",
    "reboot",
    "review",
    "ensure",
    "检查",
    "确认",
    "测量",
    "更换",
    "重启",
)

_POWER_QUERY_MARKERS = (
    "power",
    "pwr",
    "voltage",
    "电源",
    "供电",
    "电压",
    "没电",
    "断电",
)

_POWER_TEXT_MARKERS = (
    "power",
    "pwr",
    "voltage",
    "24 v",
    "24v",
    "supply",
    "电源",
    "供电",
    "电压",
)

_OFF_QUERY_MARKERS = (
    " off",
    "off?",
    "off ",
    "没电",
    "断电",
    "掉电",
    "无电",
)

_OFF_TEXT_MARKERS = (
    " off",
    "off,",
    "off.",
    "断电",
    "掉电",
    "无电",
)


@dataclass(frozen=True)
class RerankScore:
    vector_score: float
    rerank_score: float
    final_score: float


def _tokenize(value: str) -> set[str]:
    value = value.lower()
    tokens: set[str] = set(
        re.findall(r"[a-z0-9]+(?:[-_.][a-z0-9]+)*", value)
    )

    for chunk in re.findall(r"[\u4e00-\u9fff]+", value):
        if len(chunk) <= 3:
            tokens.add(chunk)
        else:
            tokens.update(
                chunk[index : index + 2]
                for index in range(len(chunk) - 1)
            )

    return {
        token
        for token in tokens
        if token not in _STOPWORDS and len(token) > 1
    }


def _contains_any(value: str, markers: tuple[str, ...]) -> bool:
    lowered = f" {value.lower()} "
    return any(marker in lowered for marker in markers)


def _query_concepts(query: str) -> list[set[str]]:
    concepts: list[set[str]] = []
    seen: set[frozenset[str]] = set()

    for token in sorted(_tokenize(query)):
        variants = set(_SYNONYM_LOOKUP.get(token, {token}))
        key = frozenset(variants)
        if key in seen:
            continue
        seen.add(key)
        concepts.append(variants)

    return concepts


def _coverage(
    query: str,
    candidate: str,
) -> float:
    concepts = _query_concepts(query)
    if not concepts:
        return 0.0

    candidate_tokens = _tokenize(candidate)
    candidate_lower = candidate.lower()

    matched = 0
    for variants in concepts:
        if any(
            variant in candidate_tokens or variant in candidate_lower
            for variant in variants
        ):
            matched += 1

    return matched / len(concepts)


def calculate_rerank_score(
    *,
    query: str,
    text: str,
    section_path: str | None,
    block_type: str,
    vector_score: float,
    vector_weight: float = VECTOR_WEIGHT,
    rerank_weight: float = RERANK_WEIGHT,
) -> RerankScore:
    section = section_path or ""

    lexical_coverage = _coverage(query, text)
    section_coverage = _coverage(query, section)

    rerank = 0.45 * lexical_coverage
    rerank += 0.10 * section_coverage

    troubleshoot_query = _contains_any(
        query,
        _TROUBLESHOOT_QUERY_MARKERS,
    )
    if troubleshoot_query and _contains_any(
        section,
        _TROUBLESHOOT_SECTION_MARKERS,
    ):
        rerank += 0.15

    if troubleshoot_query and _contains_any(
        text,
        _PROCEDURAL_TEXT_MARKERS,
    ):
        rerank += 0.12

    if _contains_any(query, _POWER_QUERY_MARKERS) and _contains_any(
        text,
        _POWER_TEXT_MARKERS,
    ):
        rerank += 0.08

    if _contains_any(query, _OFF_QUERY_MARKERS) and _contains_any(
        text,
        _OFF_TEXT_MARKERS,
    ):
        rerank += 0.06

    if block_type == "text":
        rerank += 0.04
    elif block_type == "table":
        rerank += 0.02

    rerank = min(1.0, max(0.0, rerank))
    final = (vector_weight * vector_score) + (rerank_weight * rerank)

    return RerankScore(
        vector_score=round(vector_score, 6),
        rerank_score=round(rerank, 6),
        final_score=round(final, 6),
    )
