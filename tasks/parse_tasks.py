from __future__ import annotations

import asyncio
import logging

from config.settings import settings
from tasks.celery_app import app

logger = logging.getLogger(__name__)


@app.task(name="tasks.parse_tasks.fast_parse_all")
def fast_parse_all() -> dict[str, object]:
    from application.parse_orchestrator import ParseOrchestrator

    orchestrator = ParseOrchestrator()
    results: dict[str, object] = {}
    for store in settings.STORE_NAMES:
        try:
            result = asyncio.run(orchestrator.fast_parse(store))
            results[store] = result
            logger.info("[FAST_PARSE] %s: %s", store, result)
        except Exception:
            logger.exception("[FAST_PARSE] %s failed", store)
            results[store] = {"status": "failed"}
    return results


@app.task(name="tasks.parse_tasks.full_parse_all")
def full_parse_all() -> dict[str, object]:
    from application.parse_orchestrator import ParseOrchestrator

    orchestrator = ParseOrchestrator()
    results: dict[str, object] = {}
    for store in settings.STORE_NAMES:
        try:
            result = asyncio.run(orchestrator.full_parse(store))
            results[store] = result
            logger.info("[FULL_PARSE] %s: %s", store, result)
        except Exception:
            logger.exception("[FULL_PARSE] %s failed", store)
            results[store] = {"status": "failed"}
    return results


@app.task(name="tasks.parse_tasks.discover_all")
def discover_all() -> dict[str, object]:
    from application.parse_orchestrator import ParseOrchestrator

    orchestrator = ParseOrchestrator()
    results: dict[str, object] = {}
    for store in settings.STORE_NAMES:
        try:
            result = asyncio.run(orchestrator.discover(store))
            results[store] = result
            logger.info("[DISCOVER] %s: %s", store, result)
        except Exception:
            logger.exception("[DISCOVER] %s failed", store)
            results[store] = {"status": "failed"}
    return results
