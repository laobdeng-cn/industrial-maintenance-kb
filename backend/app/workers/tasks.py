import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import PictureItem, TableItem
from sqlalchemy import delete

from app.core.config import settings
from app.core.parser import PARSER_CONFIG_VERSION
from app.db.session import SessionLocal
from app.models.content import DocumentAsset, DocumentBlock
from app.models.document import DocumentVersion
from app.models.ingestion import IngestionJob
from app.workers.celery_app import celery_app


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _bbox_to_dict(bbox: Any) -> dict[str, Any] | None:
    if bbox is None:
        return None

    if hasattr(bbox, "model_dump"):
        data = bbox.model_dump(mode="json")
        return {key: _enum_value(value) for key, value in data.items()}

    result: dict[str, Any] = {}
    for name in ("l", "t", "r", "b", "coord_origin"):
        if hasattr(bbox, name):
            result[name] = _enum_value(getattr(bbox, name))

    return result or None


def _item_label(item: Any) -> str:
    label = _enum_value(getattr(item, "label", None))
    if label:
        return str(label)
    return item.__class__.__name__.lower()


def _item_text(item: Any, doc: Any) -> str | None:
    text = getattr(item, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()

    if isinstance(item, PictureItem):
        caption_text = getattr(item, "caption_text", None)
        if callable(caption_text):
            caption = caption_text(doc)
            if isinstance(caption, str) and caption.strip():
                return caption.strip()
        return None

    exporter = getattr(item, "export_to_markdown", None)
    if callable(exporter):
        for kwargs in ({"doc": doc}, {}):
            try:
                exported = exporter(**kwargs)
            except (TypeError, ValueError):
                continue

            if isinstance(exported, str) and exported.strip():
                return exported.strip()

    return None


def _provenance_data(item: Any) -> tuple[int | None, int | None, dict[str, Any] | None]:
    provenance = list(getattr(item, "prov", None) or [])
    pages = [
        int(page_no)
        for prov in provenance
        if (page_no := getattr(prov, "page_no", None)) is not None
    ]

    page_start = min(pages) if pages else None
    page_end = max(pages) if pages else None
    bbox = _bbox_to_dict(
        getattr(provenance[0], "bbox", None)
        if provenance
        else None
    )
    return page_start, page_end, bbox


def _save_visual_asset(
    document: DocumentVersion,
    item: PictureItem | TableItem,
    docling_document: Any,
    *,
    ordinal: int,
    block_type: str,
    page_number: int | None,
    bbox: dict[str, Any] | None,
) -> DocumentAsset | None:
    image = item.get_image(docling_document)
    if image is None:
        return None

    asset_dir = (
        Path(settings.storage_root)
        / "assets"
        / document.file_hash
    )
    asset_dir.mkdir(parents=True, exist_ok=True)

    temp_path = asset_dir / f"{ordinal:04d}-{block_type}.png"
    image.save(temp_path, format="PNG")

    content = temp_path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    final_path = asset_dir / f"{ordinal:04d}-{block_type}-{digest[:12]}.png"

    if final_path != temp_path:
        if final_path.exists():
            temp_path.unlink(missing_ok=True)
        else:
            temp_path.replace(final_path)

    relative_path = final_path.relative_to(
        Path(settings.storage_root)
    ).as_posix()

    caption: str | None = None
    caption_text = getattr(item, "caption_text", None)
    if callable(caption_text):
        value = caption_text(docling_document)
        if isinstance(value, str) and value.strip():
            caption = value.strip()

    return DocumentAsset(
        document_version_id=document.id,
        asset_type=block_type,
        page_number=page_number,
        storage_path=relative_path,
        mime_type="image/png",
        sha256=digest,
        bbox=bbox,
        caption=caption,
    )


def _extract_content(
    document: DocumentVersion,
    docling_document: Any,
) -> tuple[list[DocumentBlock], list[DocumentAsset]]:
    blocks: list[DocumentBlock] = []
    assets: list[DocumentAsset] = []
    current_section: str | None = None
    ordinal = 0

    for item, level in docling_document.iterate_items():
        block_type = _item_label(item)
        text = _item_text(item, docling_document)
        is_visual = isinstance(item, (PictureItem, TableItem))

        if not text and not is_visual:
            continue

        if block_type in {"title", "section_header"} and text:
            current_section = text[:1000]

        page_start, page_end, bbox = _provenance_data(item)

        asset: DocumentAsset | None = None
        if is_visual:
            asset = _save_visual_asset(
                document=document,
                item=item,
                docling_document=docling_document,
                ordinal=ordinal,
                block_type=block_type[:30],
                page_number=page_start,
                bbox=bbox,
            )
            if asset is not None:
                assets.append(asset)

        evidence_material = text or (
            asset.sha256 if asset is not None and asset.sha256 else block_type
        )
        evidence_seed = "|".join(
            [
                document.file_hash,
                PARSER_CONFIG_VERSION,
                str(ordinal),
                str(page_start or ""),
                block_type,
                hashlib.sha256(
                    evidence_material.encode("utf-8")
                ).hexdigest(),
            ]
        )
        evidence_id = hashlib.sha256(
            evidence_seed.encode("utf-8")
        ).hexdigest()

        blocks.append(
            DocumentBlock(
                evidence_id=evidence_id,
                document_version_id=document.id,
                block_type=block_type[:30],
                section_path=current_section,
                page_start=page_start,
                page_end=page_end,
                bbox=bbox,
                text=text,
                asset=asset,
                ordinal=ordinal,
                extra_metadata={
                    "parser": "docling",
                    "parser_config_version": PARSER_CONFIG_VERSION,
                    "hierarchy_level": level,
                    "has_visual_asset": asset is not None,
                },
            )
        )
        ordinal += 1

    if blocks:
        return blocks, assets

    markdown = docling_document.export_to_markdown()
    if markdown and markdown.strip():
        evidence_seed = "|".join(
            [
                document.file_hash,
                PARSER_CONFIG_VERSION,
                "fallback",
                hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            ]
        )
        blocks.append(
            DocumentBlock(
                evidence_id=hashlib.sha256(
                    evidence_seed.encode("utf-8")
                ).hexdigest(),
                document_version_id=document.id,
                block_type="document",
                text=markdown.strip(),
                ordinal=0,
                extra_metadata={
                    "parser": "docling",
                    "parser_config_version": PARSER_CONFIG_VERSION,
                    "fallback": True,
                },
            )
        )

    return blocks, assets


def _build_converter() -> DocumentConverter:
    pipeline_options = PdfPipelineOptions()
    pipeline_options.images_scale = 1.5
    pipeline_options.generate_page_images = True
    pipeline_options.generate_picture_images = True

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options
            )
        }
    )


@celery_app.task(
    bind=True,
    name="app.workers.tasks.parse_document",
)
def parse_document(self, job_id: int) -> dict[str, Any]:
    db = SessionLocal()

    try:
        job = db.get(IngestionJob, job_id)
        if job is None:
            return {
                "job_id": job_id,
                "status": "missing",
            }

        if job.status == "succeeded":
            return {
                "job_id": job.id,
                "status": job.status,
                "stage": job.stage,
            }

        document = (
            db.get(DocumentVersion, job.document_version_id)
            if job.document_version_id is not None
            else None
        )
        if document is None:
            raise RuntimeError("document version does not exist")

        if not document.storage_path:
            raise RuntimeError("document has no storage path")

        source_path = Path(settings.storage_root) / document.storage_path
        if not source_path.is_file():
            raise FileNotFoundError(
                f"stored PDF not found: {document.storage_path}"
            )

        job.status = "running"
        job.stage = "parsing"
        job.error_message = None
        job.started_at = datetime.now(timezone.utc)
        job.completed_at = None
        db.commit()

        converter = _build_converter()
        result = converter.convert(source_path)

        blocks, assets = _extract_content(
            document=document,
            docling_document=result.document,
        )
        if not blocks:
            raise RuntimeError("Docling produced no usable content blocks")

        job.stage = "persisting"
        db.execute(
            delete(DocumentBlock).where(
                DocumentBlock.document_version_id == document.id
            )
        )
        db.execute(
            delete(DocumentAsset).where(
                DocumentAsset.document_version_id == document.id
            )
        )
        db.add_all(assets)
        db.add_all(blocks)

        job.status = "succeeded"
        job.stage = "completed"
        job.completed_at = datetime.now(timezone.utc)
        db.commit()

        return {
            "job_id": job.id,
            "document_version_id": document.id,
            "status": job.status,
            "stage": job.stage,
            "block_count": len(blocks),
            "asset_count": len(assets),
        }
    except Exception as exc:
        db.rollback()

        job = db.get(IngestionJob, job_id)
        if job is not None:
            job.status = "failed"
            job.stage = "failed"
            job.retry_count += 1
            job.error_message = str(exc)[:4000]
            job.completed_at = datetime.now(timezone.utc)
            db.commit()

        raise
    finally:
        db.close()
