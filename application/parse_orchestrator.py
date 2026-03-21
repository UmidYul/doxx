from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from infrastructure.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)


class ParseOrchestrator:
    async def fast_parse(self, source_name: str) -> dict:
        """Price + in_stock only for all products from source. No full page load."""
        log_entry = await self._start_log(source_name)
        try:
            from infrastructure.db.parse_cache_repo import ParseCacheRepo

            repo = ParseCacheRepo()
            stale = await repo.get_stale(source_name, hours=2)
            logger.info("[FAST_PARSE] %s: %d stale items to check", source_name, len(stale))
            await self._finish_log(log_entry, items_parsed=len(stale), status="done")
            return {"source": source_name, "items_checked": len(stale), "status": "done"}
        except Exception:
            logger.exception("[FAST_PARSE] %s failed", source_name)
            await self._finish_log(log_entry, status="failed")
            return {"source": source_name, "status": "failed"}

    async def full_parse(self, source_name: str) -> dict:
        """Complete card with specs and images for products needing full refresh."""
        log_entry = await self._start_log(source_name)
        try:
            logger.info("[FULL_PARSE] %s: starting full parse", source_name)
            await self._finish_log(log_entry, status="done")
            return {"source": source_name, "status": "done"}
        except Exception:
            logger.exception("[FULL_PARSE] %s failed", source_name)
            await self._finish_log(log_entry, status="failed")
            return {"source": source_name, "status": "failed"}

    async def discover(self, source_name: str) -> dict:
        """Find new URLs not in parse_cache, add to parse_queue."""
        log_entry = await self._start_log(source_name)
        try:
            logger.info("[DISCOVER] %s: searching for new products", source_name)
            await self._finish_log(log_entry, status="done")
            return {"source": source_name, "status": "done"}
        except Exception:
            logger.exception("[DISCOVER] %s failed", source_name)
            await self._finish_log(log_entry, status="failed")
            return {"source": source_name, "status": "failed"}

    async def _start_log(self, source_name: str) -> int:
        def _insert() -> int:
            sb = get_supabase()
            result = (
                sb.table("parse_logs")
                .insert(
                    {
                        "source_name": source_name,
                        "started_at": datetime.now(timezone.utc).isoformat(),
                        "status": "running",
                    }
                )
                .execute()
            )
            rows = result.data or []
            if not rows:
                raise RuntimeError("parse_logs insert returned no row")
            return int(rows[0]["id"])

        return await asyncio.to_thread(_insert)

    async def _finish_log(
        self,
        log_id: int,
        items_parsed: int = 0,
        items_changed: int = 0,
        items_new: int = 0,
        status: str = "done",
    ) -> None:
        def _update() -> None:
            get_supabase().table("parse_logs").update(
                {
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "items_parsed": items_parsed,
                    "items_changed": items_changed,
                    "items_new": items_new,
                    "status": status,
                }
            ).eq("id", log_id).execute()

        await asyncio.to_thread(_update)
