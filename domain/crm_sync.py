from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_serializer


class CrmSyncItem(BaseModel):
    """Snapshot payload for a single item sent to CRM ``/api/parser/sync``.

    The scraper always sends ``sync_mode="snapshot"``; ``change_hint`` is a
    local-only heuristic the CRM may use for routing but must not treat as the
    sole truth — the scraper is stateless.
    """

    schema_version: int = 1
    entity_key: str
    payload_hash: str

    source_name: str
    source_url: str
    source_id: str | None = None
    external_ids: dict[str, str] = Field(default_factory=dict)

    title: str
    brand: str | None = None
    category_hint: str | None = None

    price_value: int | None = None
    price_raw: str | None = None
    currency: str | None = None
    in_stock: bool | None = None

    raw_specs: dict[str, Any] = Field(default_factory=dict)
    typed_specs: dict[str, Any] = Field(default_factory=dict)
    normalization_warnings: list[str] = Field(default_factory=list)
    spec_coverage: dict[str, Any] = Field(default_factory=dict)
    field_confidence: dict[str, Any] = Field(default_factory=dict)
    suppressed_typed_fields: list[dict[str, Any]] = Field(default_factory=list)
    normalization_quality: dict[str, Any] = Field(default_factory=dict)

    description: str | None = None
    image_urls: list[str] = Field(default_factory=list)

    scraped_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    barcode: str | None = None
    model_name: str | None = None

    sync_mode: Literal["snapshot"] = "snapshot"
    change_hint: Literal["new_product", "price_update", "stock_update", "spec_update"] | None = None
    request_idempotency_key: str | None = None

    @field_serializer("scraped_at")
    def _serialize_dt(self, v: datetime) -> str:
        if v.tzinfo is None:
            v = v.replace(tzinfo=UTC)
        return v.isoformat().replace("+00:00", "Z")


class CrmSyncBatchRequest(BaseModel):
    """Wrapper for ``POST /api/parser/sync/batch``."""

    items: list[CrmSyncItem]


class CrmSyncResponse(BaseModel):
    """CRM response for a single sync operation."""

    success: bool = True
    product_id: str | None = None
    listing_id: str | None = None
    action: str | None = None
    error: str | None = None


class CrmSyncBatchResponseItem(BaseModel):
    """One element in a batch sync response."""

    entity_key: str = ""
    success: bool = True
    product_id: str | None = None
    listing_id: str | None = None
    action: str | None = None
    error: str | None = None
