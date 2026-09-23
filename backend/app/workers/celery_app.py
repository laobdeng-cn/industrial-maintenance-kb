from celery import Celery

from app.core.config import settings


celery_app = Celery(
    "industrial_maintenance_kb",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_track_started=True,
)


@celery_app.task
def ping():
    return "pong"
