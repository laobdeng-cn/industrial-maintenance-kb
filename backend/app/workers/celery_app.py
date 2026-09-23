from celery import Celery

from app.core.config import settings


celery_app = Celery(
    "industrial_maintenance_kb",
    broker=settings.redis_url,
    backend=settings.redis_url,
)


@celery_app.task
def ping():
    return "pong"