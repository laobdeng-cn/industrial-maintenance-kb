from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.document import DocumentVersion
from app.models.equipment import EquipmentModel
from app.schemas.search import SearchHitResponse, SearchRequest, SearchResponse
from app.services.embedding import embed_query
from app.services.reranker import ROUGH_RECALL_LIMIT, calculate_rerank_score
from app.services.vector_store import search_points


def retrieve_evidence(payload: SearchRequest, db: Session) -> SearchResponse:
    if db.get(EquipmentModel, payload.equipment_model_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="equipment model not found",
        )

    candidate_limit = max(ROUGH_RECALL_LIMIT, payload.limit)

    try:
        query_vector = embed_query(payload.query)
        points = search_points(
            query_vector,
            equipment_model_id=payload.equipment_model_id,
            candidate_limit=candidate_limit,
            score_threshold=payload.score_threshold,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"vector search failed: {exc}",
        ) from exc

    document_ids = {
        int(point.payload["document_id"])
        for point in points
        if point.payload and "document_id" in point.payload
    }

    valid_document_ids: set[int] = set()
    if document_ids:
        documents = db.scalars(
            select(DocumentVersion)
            .options(selectinload(DocumentVersion.equipment_models))
            .where(DocumentVersion.id.in_(document_ids))
        ).all()

        for document in documents:
            if document.status != "published":
                continue
            equipment_ids = {model.id for model in document.equipment_models}
            if payload.equipment_model_id in equipment_ids:
                valid_document_ids.add(document.id)

    reranked_hits: list[SearchHitResponse] = []
    for point in points:
        point_payload = point.payload or {}
        document_id = int(point_payload.get("document_id", 0))
        if document_id not in valid_document_ids:
            continue

        text = str(point_payload.get("text") or "").strip()
        if not text:
            continue

        block_type = str(point_payload.get("block_type") or "")
        section_path = (
            str(point_payload["section_path"])
            if point_payload.get("section_path") is not None
            else None
        )

        scores = calculate_rerank_score(
            query=payload.query,
            text=text,
            section_path=section_path,
            block_type=block_type,
            vector_score=float(point.score),
        )

        reranked_hits.append(
            SearchHitResponse(
                score=scores.final_score,
                vector_score=scores.vector_score,
                rerank_score=scores.rerank_score,
                final_score=scores.final_score,
                point_id=point.id,
                document_id=document_id,
                block_id=int(point_payload["block_id"]),
                evidence_id=str(point_payload["evidence_id"]),
                title=str(point_payload.get("title") or ""),
                version=str(point_payload["version"]) if point_payload.get("version") is not None else None,
                language=str(point_payload["language"]) if point_payload.get("language") is not None else None,
                block_type=block_type,
                section_path=section_path,
                page_start=int(point_payload["page_start"]) if point_payload.get("page_start") is not None else None,
                page_end=int(point_payload["page_end"]) if point_payload.get("page_end") is not None else None,
                asset_id=int(point_payload["asset_id"]) if point_payload.get("asset_id") is not None else None,
                text=text,
            )
        )

    reranked_hits.sort(
        key=lambda hit: (hit.final_score, hit.vector_score),
        reverse=True,
    )

    return SearchResponse(
        query=payload.query,
        equipment_model_id=payload.equipment_model_id,
        embedding_model=settings.embedding_model,
        collection_name=settings.qdrant_collection,
        rough_recall_limit=candidate_limit,
        hits=reranked_hits[:payload.limit],
    )
