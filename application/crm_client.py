from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from domain.events import BaseEvent, CRMSyncResponse

logger = logging.getLogger(__name__)


class CRMUnavailableError(Exception):
    pass


class CRMClient:
    def __init__(self) -> None:
        from config.settings import settings

        self.base_url = settings.CRM_API_URL
        self.headers = {
            "X-Parser-Key": settings.CRM_API_KEY,
            "Content-Type": "application/json",
        }
        self.timeout = httpx.Timeout(10.0)

    async def sync_event(self, event: BaseEvent) -> CRMSyncResponse | None:
        async with httpx.AsyncClient(base_url=self.base_url, headers=self.headers, timeout=self.timeout) as client:
            try:
                response = await client.post("/parser/sync", json=event.model_dump(mode="json"))
                if response.status_code == 200:
                    logger.info("[CRM_SYNC] Event %s sent successfully", event.event)
                    return CRMSyncResponse(**response.json())
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", "60"))
                    logger.warning("[CRM_SYNC] Rate limited, waiting %ds", retry_after)
                    await asyncio.sleep(retry_after)
                    response = await client.post("/parser/sync", json=event.model_dump(mode="json"))
                    if response.status_code == 200:
                        return CRMSyncResponse(**response.json())
                logger.warning("[CRM_SYNC] Unexpected status %d", response.status_code)
                return None
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                logger.error("[CRM_UNAVAILABLE] %s", exc)
                raise CRMUnavailableError(str(exc)) from exc

    async def sync_event_raw(self, payload: dict[str, Any]) -> CRMSyncResponse | None:
        async with httpx.AsyncClient(base_url=self.base_url, headers=self.headers, timeout=self.timeout) as client:
            try:
                response = await client.post("/parser/sync", json=payload)
                if response.status_code == 200:
                    logger.info("[CRM_SYNC] Raw event %s sent successfully", payload.get("event"))
                    return CRMSyncResponse(**response.json())
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", "60"))
                    logger.warning("[CRM_SYNC] Rate limited (raw), waiting %ds", retry_after)
                    await asyncio.sleep(retry_after)
                    response = await client.post("/parser/sync", json=payload)
                    if response.status_code == 200:
                        return CRMSyncResponse(**response.json())
                logger.warning("[CRM_SYNC] Unexpected status %d (raw)", response.status_code)
                return None
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                logger.error("[CRM_UNAVAILABLE] %s", exc)
                raise CRMUnavailableError(str(exc)) from exc

    async def sync_batch(self, events: list[BaseEvent]) -> list[CRMSyncResponse]:
        results: list[CRMSyncResponse] = []
        for i in range(0, len(events), 100):
            chunk = events[i : i + 100]
            async with httpx.AsyncClient(base_url=self.base_url, headers=self.headers, timeout=self.timeout) as client:
                try:
                    payload = {"events": [e.model_dump(mode="json") for e in chunk]}
                    response = await client.post("/parser/sync/batch", json=payload)
                    if response.status_code == 200:
                        data = response.json()
                        results.extend([CRMSyncResponse(**r) for r in data.get("results", [])])
                        logger.info("[CRM_BATCH] Sent %d events", len(chunk))
                    else:
                        logger.warning("[CRM_SYNC] Batch unexpected status %d", response.status_code)
                except (httpx.ConnectError, httpx.TimeoutException) as exc:
                    logger.error("[CRM_UNAVAILABLE] Batch failed: %s", exc)
                    raise CRMUnavailableError(str(exc)) from exc
        return results

    async def find_in_catalog(self, source: str, source_id: str) -> CRMSyncResponse | None:
        async with httpx.AsyncClient(base_url=self.base_url, headers=self.headers, timeout=self.timeout) as client:
            try:
                response = await client.get(
                    "/parser/catalog/find",
                    params={"source": source, "source_id": source_id},
                )
                if response.status_code == 200:
                    return CRMSyncResponse(**response.json())
                if response.status_code == 404:
                    return None
                logger.warning("[CRM_SYNC] catalog/find returned %d", response.status_code)
                return None
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                logger.error("[CRM_UNAVAILABLE] catalog/find: %s", exc)
                return None
