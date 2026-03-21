from __future__ import annotations

import logging

from application.crm_client import CRMClient, CRMUnavailableError
from domain.events import BaseEvent, CRMSyncResponse
from infrastructure.db.event_repo import EventRepo

logger = logging.getLogger(__name__)


class EventSender:
    def __init__(self, crm_client: CRMClient | None = None) -> None:
        self.crm_client = crm_client or CRMClient()

    async def send_event_detail(self, event: BaseEvent) -> tuple[bool, CRMSyncResponse | None]:
        try:
            response = await self.crm_client.sync_event(event)
            if response and response.status == "ok":
                logger.info("[CRM_SYNC] %s sent, crm_listing_id=%s", event.event, response.crm_listing_id)
                return True, response
            logger.warning("[CRM_SYNC] %s failed, response=%s", event.event, response)
            return False, response
        except CRMUnavailableError:
            logger.warning("[CRM_UNAVAILABLE] Saving %s to pending_events", event.event)
            repo = EventRepo()
            await repo.save_pending(event)
            return False, None
        except Exception:
            logger.exception("[CRM_SYNC] Unexpected error sending %s", event.event)
            repo = EventRepo()
            await repo.save_pending(event)
            return False, None

    async def send_event(self, event: BaseEvent) -> bool:
        ok, _ = await self.send_event_detail(event)
        return ok

    async def send_batch(self, events: list[BaseEvent]) -> tuple[int, int]:
        sent, failed = 0, 0
        try:
            responses = await self.crm_client.sync_batch(events)
            sent = len(responses)
            failed = len(events) - sent
        except CRMUnavailableError:
            logger.warning("[CRM_UNAVAILABLE] Batch failed, saving %d events to pending", len(events))
            repo = EventRepo()
            for event in events:
                await repo.save_pending(event)
            failed = len(events)
        return sent, failed

    async def flush_pending(self) -> tuple[int, int]:
        sent, failed = 0, 0
        repo = EventRepo()
        pending = await repo.get_pending(limit=100)
        if not pending:
            return 0, 0
        for pe in pending:
            try:
                response = await self.crm_client.sync_event_raw(pe.payload)
                if response and response.status == "ok":
                    await repo.mark_sent(pe.id)
                    sent += 1
                else:
                    await repo.increment_retry(pe.id, "CRM returned non-ok")
                    failed += 1
            except CRMUnavailableError as exc:
                await repo.increment_retry(pe.id, str(exc))
                failed += 1
                new_retry = pe.retry_count + 1
                if new_retry >= 10:
                    await repo.mark_failed(pe.id, f"Max retries reached: {exc}")
                    logger.error(
                        "[CRM_RETRY] Event %d failed permanently after %d retries",
                        pe.id,
                        new_retry,
                    )
                    try:
                        import sentry_sdk

                        sentry_sdk.capture_message(f"Event {pe.id} failed permanently")
                    except ImportError:
                        pass
        return sent, failed
