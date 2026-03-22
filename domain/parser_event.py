from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_serializer

from domain.crm_lifecycle import CrmIdentityContext, ParserLifecycleEventType
from domain.crm_sync import CrmSyncItem

ParserEventType = ParserLifecycleEventType


class ParserSyncEvent(BaseModel):
    """Envelope for one parser→CRM sync attempt (snapshot + operational metadata).

    ``event_id`` is unique per delivery attempt; ``payload_hash`` duplicates
    ``data.payload_hash`` (business fingerprint only — not driven by event metadata).
    ``identity`` carries the runtime CRM id bridge for lifecycle-aware routing.
    """

    event_id: str
    event_type: ParserEventType = "product_found"
    sent_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    identity: CrmIdentityContext
    payload_hash: str
    data: CrmSyncItem
    request_idempotency_key: str = ""
    replay_mode: str = "snapshot_upsert"
    original_intent_event_type: ParserEventType | None = None
    normalized_for_reconcile: dict[str, object] | None = Field(default=None, exclude=True)

    @field_serializer("sent_at")
    def _serialize_sent_at(self, v: datetime) -> str:
        if v.tzinfo is None:
            v = v.replace(tzinfo=UTC)
        return v.isoformat().replace("+00:00", "Z")
