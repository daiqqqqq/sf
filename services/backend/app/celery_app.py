from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "rag_platform",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.pipeline"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=False,
    beat_schedule={
        "probe-services-every-5-minutes": {
            "task": "app.tasks.pipeline.probe_services_task",
            "schedule": 300.0,
        }
    },
)
celery_app.autodiscover_tasks(["app.tasks"])
