from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

try:
    from postgrest.exceptions import APIError as PostgrestAPIError
except ImportError:

    class PostgrestAPIError(Exception):
        pass

from infrastructure.db.errors import DBError
from infrastructure.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)


class StoreRepo:
    STORE_TABLE_MAP = {
        "mediapark": "mediapark_products",
        "olx": "olx_products",
        "texnomart": "texnomart_products",
        "makro": "makro_products",
        "uzum": "uzum_products",
    }

    def __init__(self, session: Any | None = None) -> None:
        self._session = session
        self.db = get_supabase()

    def upsert_product(self, source: str, data: dict[str, Any]) -> dict[str, Any]:
        table = self.STORE_TABLE_MAP.get(source)
        if not table:
            raise DBError(f"Unknown store source: {source}")
        row = dict(data)
        rh = row.get("raw_html")
        if rh is not None and isinstance(rh, str) and len(rh) > 50_000:
            row = {**row, "raw_html": None}
        if "parsed_at" not in row:
            row["parsed_at"] = datetime.now(timezone.utc).isoformat()
        if "price" in row and isinstance(row["price"], Decimal):
            row["price"] = float(row["price"])
        try:
            result = self.db.table(table).upsert(row, on_conflict="url").execute()
        except PostgrestAPIError as exc:
            logger.error("[SUPABASE_ERROR] upsert_product source=%s url=%s err=%s", source, row.get("url"), exc)
            raise DBError(str(exc)) from exc
        rows = result.data or []
        if not rows:
            raise DBError(f"{table} upsert returned no row")
        return rows[0]
