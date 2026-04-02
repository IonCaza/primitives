from celery import Celery

from app.config import settings

celery = Celery("myapp", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_hijack_root_logger=False,
    task_create_missing_queues=True,
    include=["app.workers.tasks"],
)
