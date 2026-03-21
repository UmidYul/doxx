from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID


def _to_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _to_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        s = value.replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    return None


@dataclass
class ParseCacheRecord:
    """Row from parse_cache — attribute-compatible with former SQLAlchemy model."""

    url: str
    source_name: str
    source_id: str | None
    last_price: Decimal | None
    last_in_stock: bool | None
    last_parsed_at: datetime | None
    crm_listing_id: UUID | None
    crm_product_id: UUID | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> ParseCacheRecord:
        return cls(
            url=str(row["url"]),
            source_name=str(row["source_name"]),
            source_id=str(row["source_id"]) if row.get("source_id") is not None else None,
            last_price=_to_decimal(row.get("last_price")),
            last_in_stock=row.get("last_in_stock"),
            last_parsed_at=_to_dt(row.get("last_parsed_at")),
            crm_listing_id=_to_uuid(row.get("crm_listing_id")),
            crm_product_id=_to_uuid(row.get("crm_product_id")),
        )


@dataclass
class PendingEventRecord:
    """Row from pending_events — attribute-compatible with former ORM instance."""

    id: int
    event_type: str
    payload: dict[str, Any]
    created_at: datetime | None
    retry_count: int
    last_error: str | None
    status: str

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> PendingEventRecord:
        raw_payload = row.get("payload")
        if isinstance(raw_payload, dict):
            payload: dict[str, Any] = raw_payload
        elif isinstance(raw_payload, str):
            payload = json.loads(raw_payload)
        else:
            payload = dict(raw_payload) if raw_payload is not None else {}
        return cls(
            id=int(row["id"]),
            event_type=str(row["event_type"]),
            payload=payload,
            created_at=_to_dt(row.get("created_at")),
            retry_count=int(row.get("retry_count") or 0),
            last_error=str(row["last_error"]) if row.get("last_error") is not None else None,
            status=str(row.get("status") or "pending"),
        )
