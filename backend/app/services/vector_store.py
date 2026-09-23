from functools import lru_cache
from typing import Any

from qdrant_client import QdrantClient, models

from app.core.config import settings


@lru_cache(maxsize=1)
def get_qdrant_client() -> QdrantClient:
    return QdrantClient(
        url=settings.qdrant_url,
        timeout=30,
    )


def ensure_collection() -> None:
    client = get_qdrant_client()
    collection_name = settings.qdrant_collection

    if not client.collection_exists(collection_name):
        client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(
                size=settings.embedding_vector_size,
                distance=models.Distance.COSINE,
            ),
        )

    info = client.get_collection(collection_name)
    payload_schema = info.payload_schema or {}

    required_indexes: dict[str, models.PayloadSchemaType] = {
        "document_id": models.PayloadSchemaType.INTEGER,
        "equipment_model_ids": models.PayloadSchemaType.INTEGER,
        "status": models.PayloadSchemaType.KEYWORD,
        "block_type": models.PayloadSchemaType.KEYWORD,
        "language": models.PayloadSchemaType.KEYWORD,
    }

    for field_name, field_schema in required_indexes.items():
        if field_name in payload_schema:
            continue

        client.create_payload_index(
            collection_name=collection_name,
            field_name=field_name,
            field_schema=field_schema,
            wait=True,
        )


def delete_document_points(document_id: int) -> None:
    client = get_qdrant_client()
    collection_name = settings.qdrant_collection

    if not client.collection_exists(collection_name):
        return

    client.delete(
        collection_name=collection_name,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id",
                        match=models.MatchValue(value=document_id),
                    )
                ]
            )
        ),
        wait=True,
    )


def upload_points(points: list[models.PointStruct]) -> None:
    if not points:
        return

    ensure_collection()
    get_qdrant_client().upload_points(
        collection_name=settings.qdrant_collection,
        points=points,
        wait=True,
    )


def search_points(
    query_vector: list[float],
    *,
    equipment_model_id: int,
    candidate_limit: int,
    score_threshold: float | None,
) -> list[Any]:
    ensure_collection()

    result = get_qdrant_client().query_points(
        collection_name=settings.qdrant_collection,
        query=query_vector,
        query_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="status",
                    match=models.MatchValue(value="published"),
                ),
                models.FieldCondition(
                    key="equipment_model_ids",
                    match=models.MatchValue(value=equipment_model_id),
                ),
            ]
        ),
        limit=candidate_limit,
        score_threshold=score_threshold,
        with_payload=True,
        with_vectors=False,
    )

    return list(result.points)
