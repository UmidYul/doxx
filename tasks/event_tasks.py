from __future__ import annotations

import asyncio
import logging

from tasks.celery_app import app

logger = logging.getLogger(__name__)


@app.task(name="tasks.event_tasks.retry_pending")
def retry_pending() -> dict[str, int]:
    from application.event_sender import EventSender

    sender = EventSender()
    try:
        sent, failed = asyncio.run(sender.flush_pending())
        logger.info("[CRM_RETRY] sent=%d failed=%d", sent, failed)
        return {"sent": sent, "failed": failed}
    except Exception:
        logger.exception("[CRM_RETRY] Failed to flush pending events")
        return {"sent": 0, "failed": -1}
