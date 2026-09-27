from celery import Celery
from core.config import settings
import os

os.environ.setdefault("ENVIRONMENT", "production")

celery_app = Celery(
    "solvenow_worker",
    broker=settings.CELERY_BROKER_URL or settings.REDIS_CONNECTION_URL,
    backend=settings.CELERY_RESULT_BACKEND or settings.REDIS_CONNECTION_URL,
    include=["worker.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
)

if __name__ == '__main__':
    celery_app.start()

