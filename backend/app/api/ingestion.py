from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.models.ingestion import IngestionJob
from app.schemas.document import IngestionJobResponse
from app.workers.celery_app import celery_app


router = APIRouter(
    prefix="/api/ingestion-jobs",
    tags=["ingestion"],
)

PARSE_TASK_NAME = "app.workers.tasks.parse_document"


@router.get(
    "/{job_id}",
    response_model=IngestionJobResponse,
)
def get_ingestion_job(
    job_id: int,
    db: Session = Depends(get_db),
) -> IngestionJobResponse:
    job = db.get(IngestionJob, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ingestion job not found",
        )

    return IngestionJobResponse.model_validate(job)


@router.post(
    "/{job_id}/enqueue",
    response_model=IngestionJobResponse,
)
def enqueue_ingestion_job(
    job_id: int,
    db: Session = Depends(get_db),
) -> IngestionJobResponse:
    job = db.get(IngestionJob, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ingestion job not found",
        )

    if job.status == "succeeded":
        return IngestionJobResponse.model_validate(job)

    if job.status == "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="ingestion job is already running",
        )

    job.status = "pending"
    job.stage = "queued"
    job.error_message = None
    job.started_at = None
    job.completed_at = None
    db.commit()
    db.refresh(job)

    try:
        celery_app.send_task(
            PARSE_TASK_NAME,
            args=[job.id],
        )
    except Exception as exc:
        job.error_message = f"failed to enqueue task: {exc}"[:4000]
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="failed to enqueue ingestion task",
        ) from exc

    return IngestionJobResponse.model_validate(job)
