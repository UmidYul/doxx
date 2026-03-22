from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

ParserLifecycleEventType = Literal["product_found", "price_changed", "out_of_stock", "characteristic_added"]

CrmLifecycleAction = Literal["created", "matched", "needs_review", "updated", "ignored"]


class CrmIdentityContext(BaseModel):
    """Runtime + stable identity bridge for parser↔CRM (not catalog truth)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    entity_key: str
    external_ids: dict[str, str] = Field(default_factory=dict)
    barcode: str | None = None
    source_name: str
    source_url: str
    source_id: str | None = None
    crm_listing_id: str | None = None
    crm_product_id: str | None = None


class ParserLifecycleEvent(BaseModel):
    """Logical lifecycle envelope (serializable); ``data`` mirrors CRM snapshot dict."""

    model_config = ConfigDict(str_strip_whitespace=True)

    event_id: str
    event_type: ParserLifecycleEventType
    sent_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    identity: CrmIdentityContext
    payload_hash: str
    data: dict[str, object]
    # --- 4C replay / idempotency (CRM contract metadata) ---
    request_idempotency_key: str = ""
    replay_mode: str = "snapshot_upsert"
    original_intent_event_type: ParserLifecycleEventType | None = None

    @field_serializer("sent_at")
    def _serialize_sent_at(self, v: datetime) -> str:
        if v.tzinfo is None:
            v = v.replace(tzinfo=UTC)
        return v.isoformat().replace("+00:00", "Z")


class LifecycleDecision(BaseModel):
    """Outcome of lifecycle policy for one delivery attempt."""

    model_config = ConfigDict(str_strip_whitespace=True)

    selected_event_type: ParserLifecycleEventType
    allowed: bool
    fallback_applied: bool
    fallback_reason: str | None = None
    required_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
