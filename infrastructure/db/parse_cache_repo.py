from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

try:
    from postgrest.exceptions import APIError as PostgrestAPIError
except ImportError:

    class PostgrestAPIError(Exception):
        """Placeholder if postgrest is not installed."""

        pass

from infrastructure.db.errors import DBError
from infrastructure.db.records import ParseCacheRecord
from infrastructure.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)


class ParseCacheRepo:
    """parse_cache access via Supabase. `session` is accepted for backward compatibility and ignored."""

    def __init__(self, session: Any | None = None) -> None:
        self._session = session

    def _sb(self):
        return get_supabase()

    async def get_by_url(self, url: str) -> ParseCacheRecord | None:
        def _run() -> ParseCacheRecord | None:
            try:
                result = (
                    self._sb()
                    .table("parse_cache")
                    .select("*")
                    .eq("url", url)
                    .limit(1)
                    .execute()
                )
            except PostgrestAPIError as exc:
                logger.error("[SUPABASE_ERROR] get_by_url url=%s err=%s", url, exc)
                raise DBError(str(exc)) from exc
            rows = result.data or []
            if not rows:
                return None
            return ParseCacheRecord.from_row(rows[0])

        return await asyncio.to_thread(_run)

    async def upsert(
        self,
        url: str,
        source_name: str,
        source_id: str | None,
        price: Decimal | None,
        in_stock: bool | None,
        crm_listing_id: uuid.UUID | None = None,
        crm_product_id: uuid.UUID | None = None,
    ) -> ParseCacheRecord:
        def _run() -> ParseCacheRecord:
            now_iso = datetime.now(timezone.utc).isoformat()
            data: dict[str, Any] = {
                "url": url,
                "source_name": source_name,
                "source_id": str(source_id) if source_id else None,
                "last_price": float(price) if price is not None else None,
                "last_in_stock": in_stock,
                "last_parsed_at": now_iso,
                "crm_listing_id": str(crm_listing_id) if crm_listing_id else None,
                "crm_product_id": str(crm_product_id) if crm_product_id else None,
            }
            try:
                result = (
                    self._sb()
                    .table("parse_cache")
                    .upsert(data, on_conflict="url")
                    .execute()
                )
            except PostgrestAPIError as exc:
                logger.error("[SUPABASE_ERROR] upsert url=%s err=%s", url, exc)
                raise DBError(str(exc)) from exc
            rows = result.data or []
            if not rows:
                raise DBError("parse_cache upsert returned no row")
            return ParseCacheRecord.from_row(rows[0])

        return await asyncio.to_thread(_run)

    async def update_crm_ids(
        self,
        url: str,
        crm_listing_id: uuid.UUID,
        crm_product_id: uuid.UUID,
    ) -> None:
        def _run() -> None:
            payload = {
                "crm_listing_id": str(crm_listing_id),
                "crm_product_id": str(crm_product_id),
            }
            try:
                self._sb().table("parse_cache").update(payload).eq("url", url).execute()
            except PostgrestAPIError as exc:
                logger.error("[SUPABASE_ERROR] update_crm_ids url=%s err=%s", url, exc)
                raise DBError(str(exc)) from exc

        await asyncio.to_thread(_run)

    async def mark_parsed(self, url: str) -> None:
        def _run() -> None:
            now_iso = datetime.now(timezone.utc).isoformat()
            try:
                self._sb().table("parse_cache").update({"last_parsed_at": now_iso}).eq("url", url).execute()
            except PostgrestAPIError as exc:
                logger.error("[SUPABASE_ERROR] mark_parsed url=%s err=%s", url, exc)
                raise DBError(str(exc)) from exc

        await asyncio.to_thread(_run)

    async def get_stale(self, source_name: str, hours: int = 2) -> list[ParseCacheRecord]:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

        def _run() -> list[ParseCacheRecord]:
            try:
                result = (
                    self._sb()
                    .table("parse_cache")
                    .select("*")
                    .eq("source_name", source_name)
                    .or_(f"last_parsed_at.is.null,last_parsed_at.lt.{cutoff}")
                    .execute()
                )
            except PostgrestAPIError as exc:
                logger.error("[SUPABASE_ERROR] get_stale source=%s err=%s", source_name, exc)
                raise DBError(str(exc)) from exc
            return [ParseCacheRecord.from_row(r) for r in (result.data or [])]

        return await asyncio.to_thread(_run)
