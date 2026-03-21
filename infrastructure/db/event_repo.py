from __future__ import annotations

import asyncio
import logging
from typing import Any

try:
    from postgrest.exceptions import APIError as PostgrestAPIError
except ImportError:

    class PostgrestAPIError(Exception):
        pass

from domain.events import BaseEvent
from infrastructure.db.errors import DBError
from infrastructure.db.records import PendingEventRecord
from infrastructure.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)


class EventRepo:
    """pending_events via Supabase. `session` is accepted for backward compatibility and ignored."""

    def __init__(self, session: Any | None = None) -> None:
        self._session = session

    def _sb(self):
        return get_supabase()

    async def save_pending(self, event: BaseEvent) -> PendingEventRecord:
        def _run() -> PendingEventRecord:
            data = {
                "event_type": event.event,
                "payload": event.model_dump(mode="json"),
                "status": "pending",
                "retry_count": 0,
            }
            try:
                result = self._sb().table("pending_events").insert(data).execute()
            except PostgrestAPIError as exc:
                logger.error("[SUPABASE_ERROR] save_pending event=%s err=%s", event.event, exc)
                raise DBError(str(exc)) from exc
            rows = result.data or []
            if not rows:
                raise DBError("pending_events insert returned no row")
            return PendingEventRecord.from_row(rows[0])

        return await asyncio.to_thread(_run)

    async def get_pending(self, limit: int = 100) -> list[PendingEventRecord]:
        def _run() -> list[PendingEventRecord]:
            try:
                result = (
                    self._sb()
                    .table("pending_events")
                    .select("*")
                    .eq("status", "pending")
                    .lt("retry_count", 10)
                    .order("created_at", desc=False)
                    .limit(limit)
                    .execute()
                )
            except PostgrestAPIError as exc:
                logger.error("[SUPABASE_ERROR] get_pending err=%s", exc)
                raise DBError(str(exc)) from exc
            return [PendingEventRecord.from_row(r) for r in (result.data or [])]

        return await asyncio.to_thread(_run)

    async def mark_sent(self, event_id: int) -> None:
        def _run() -> None:
            try:
                self._sb().table("pending_events").update({"status": "sent"}).eq("id", event_id).execute()
            except PostgrestAPIError as exc:
                logger.error("[SUPABASE_ERROR] mark_sent id=%s err=%s", event_id, exc)
                raise DBError(str(exc)) from exc

        await asyncio.to_thread(_run)

    async def mark_failed(self, event_id: int, error: str) -> None:
        def _run() -> None:
            try:
                self._sb().table("pending_events").update(
                    {"status": "failed", "last_error": error[:500]}
                ).eq("id", event_id).execute()
            except PostgrestAPIError as exc:
                logger.error("[SUPABASE_ERROR] mark_failed id=%s err=%s", event_id, exc)
                raise DBError(str(exc)) from exc

        await asyncio.to_thread(_run)

    async def increment_retry(self, event_id: int, error: str) -> None:
        def _run() -> None:
            try:
                self._sb().rpc(
                    "increment_retry",
                    {"event_id": event_id, "err": error},
                ).execute()
            except PostgrestAPIError as exc:
                logger.error("[SUPABASE_ERROR] increment_retry id=%s err=%s", event_id, exc)
                raise DBError(str(exc)) from exc

        await asyncio.to_thread(_run)
