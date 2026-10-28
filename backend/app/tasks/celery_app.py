from __future__ import annotations

from celery import Celery

from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level, settings.log_json)

celery_app = Celery(
    "jobpilot",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.maintenance_tasks",
        "app.tasks.resume_tasks",
        "app.tasks.matching_tasks",
        "app.tasks.application_tasks",
        "app.tasks.schedule_tasks",
        "app.tasks.sheets_tasks",
        "app.tasks.account_tasks",
        "app.tasks.search_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    result_expires=86400,
    task_default_queue="default",
    # Tests run tasks inline instead of through Redis.
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=settings.celery_task_always_eager,
    # Longest send countdown is 120 s; keep the visibility timeout well above it.
    broker_transport_options={"visibility_timeout": 3600},
    task_routes={
        "app.tasks.resume_tasks.parse_resume": {"queue": "llm"},
        "app.tasks.search_tasks.*": {"queue": "scrape"},
        "app.tasks.matching_tasks.*": {"queue": "llm"},
        "app.tasks.application_tasks.*": {"queue": "llm"},
        "app.tasks.email_tasks.*": {"queue": "email"},
        "app.tasks.tracking_tasks.*": {"queue": "sync"},
        "app.tasks.sheets_tasks.*": {"queue": "sync"},
    },
    beat_schedule={
        "worker-heartbeat": {
            "task": "app.tasks.maintenance_tasks.heartbeat",
            "schedule": 60.0,
        },
        "purge-deleted-accounts": {
            "task": "app.tasks.account_tasks.purge_pending_accounts",
            "schedule": 3600.0,
        },
        "daily-searches": {
            "task": "app.tasks.schedule_tasks.dispatch_daily_searches",
            "schedule": 600.0,
        },
    },
)

# `celery -A app.tasks.celery_app` looks for `app` or `celery` in the module.
app = celery_app
