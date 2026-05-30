import os
import re

from celery import Celery
from celery.schedules import crontab

_redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
_celery_backend = re.sub(r"/\d+$", "/1", _redis_url)

celery_app = Celery(
    "qx-tasks",
    broker=_redis_url,
    backend=_celery_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Europe/Paris",
    enable_utc=True,
    task_routes={
        "core.features.compliance.tasks.*": {"queue": "compliance"},
        "core.features.audit.tasks.*": {"queue": "reports"},
        "core.features.assets.tasks.*": {"queue": "fabric_events"}
    },
    beat_schedule={
        "check-kyc-expiry": {
            "task": "core.features.compliance.tasks.check_kyc_expiry",
            "schedule": crontab(hour=2, minute=0),
            "options": {"queue": "compliance"}
        },
        "periodic-aml-screening": {
            "task": "core.features.compliance.tasks.run_periodic_aml_screening",
            "schedule": crontab(hour=3, minute=0, day_of_week=1),
            "options": {"queue": "compliance"}
        }
    }
)
