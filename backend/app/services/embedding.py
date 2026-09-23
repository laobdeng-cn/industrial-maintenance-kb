from functools import lru_cache
from pathlib import Path

from fastembed import TextEmbedding

from app.core.config import settings


@lru_cache(maxsize=1)
def get_embedding_model() -> TextEmbedding:
    cache_dir = Path(settings.embedding_cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    return TextEmbedding(
        model_name=settings.embedding_model,
        cache_dir=str(cache_dir),
    )


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    model = get_embedding_model()
    return [
        vector.tolist()
        for vector in model.embed(texts)
    ]


def embed_query(text: str) -> list[float]:
    model = get_embedding_model()
    vector = next(model.query_embed(text))
    return vector.tolist()
