from dataclasses import dataclass

from app.core.config import settings
from app.services.reranker import (
    RERANK_WEIGHT,
    ROUGH_RECALL_LIMIT,
    VECTOR_WEIGHT,
)


@dataclass(frozen=True)
class RuntimeTuning:
    rough_recall_limit: int
    vector_weight: float
    rerank_weight: float
    grounding_min_final_score: float
    grounding_min_rerank_score: float

    @classmethod
    def defaults(cls) -> "RuntimeTuning":
        return cls(
            rough_recall_limit=ROUGH_RECALL_LIMIT,
            vector_weight=VECTOR_WEIGHT,
            rerank_weight=RERANK_WEIGHT,
            grounding_min_final_score=settings.grounding_min_final_score,
            grounding_min_rerank_score=settings.grounding_min_rerank_score,
        )

    @classmethod
    def from_overrides(
        cls,
        *,
        rough_recall_limit: int | None = None,
        vector_weight: float | None = None,
        rerank_weight: float | None = None,
        grounding_min_final_score: float | None = None,
        grounding_min_rerank_score: float | None = None,
    ) -> "RuntimeTuning":
        defaults = cls.defaults()
        return cls(
            rough_recall_limit=rough_recall_limit if rough_recall_limit is not None else defaults.rough_recall_limit,
            vector_weight=vector_weight if vector_weight is not None else defaults.vector_weight,
            rerank_weight=rerank_weight if rerank_weight is not None else defaults.rerank_weight,
            grounding_min_final_score=grounding_min_final_score if grounding_min_final_score is not None else defaults.grounding_min_final_score,
            grounding_min_rerank_score=grounding_min_rerank_score if grounding_min_rerank_score is not None else defaults.grounding_min_rerank_score,
        )
