"""Celery application configuration."""

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "rag_worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,  # Don't ack until task completes (prevents lost tasks)
    worker_prefetch_multiplier=1,  # One task at a time per worker process
    task_track_started=True,
)

# Auto-discover tasks in workers module
celery_app.autodiscover_tasks(["app.workers"])
