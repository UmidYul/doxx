from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from config.settings import settings

app = Celery("uz_tech_scraper")
app.conf.broker_url = settings.CELERY_BROKER_URL
app.conf.result_backend = settings.CELERY_RESULT_BACKEND
app.conf.task_serializer = "json"
app.conf.result_serializer = "json"
app.conf.accept_content = ["json"]
app.conf.timezone = "Asia/Tashkent"
app.conf.enable_utc = True

app.conf.beat_schedule = {
    "fast-parse-all": {
        "task": "tasks.parse_tasks.fast_parse_all",
        "schedule": crontab(minute=0, hour="*/2"),
    },
    "full-parse-all": {
        "task": "tasks.parse_tasks.full_parse_all",
        "schedule": crontab(hour=0, day_of_week=0),
    },
    "discover-all": {
        "task": "tasks.parse_tasks.discover_all",
        "schedule": crontab(hour=3, minute=0),
    },
    "retry-events": {
        "task": "tasks.event_tasks.retry_pending",
        "schedule": crontab(minute="*/5"),
    },
}

# Register tasks (autodiscover looks for tasks.tasks; we use split modules).
from tasks import event_tasks as _event_tasks  # noqa: F401
from tasks import parse_tasks as _parse_tasks  # noqa: F401
