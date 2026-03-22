from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReplayMode = Literal["snapshot_upsert", "delta_if_possible", "reconcile_only"]

IdempotencyScope = Literal["entity_payload", "entity_only", "event_only"]


class ReplayDecision(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    replay_mode: ReplayMode = "snapshot_upsert"
    idempotency_scope: IdempotencyScope = "entity_payload"
    request_idempotency_key: str
    selected_event_type: str
    fallback_to_product_found: bool = False
    reason: str | None = None
    safe_to_resend: bool = True


class ReconciliationDecision(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    should_reconcile: bool = False
    reconcile_via: Literal["none", "catalog_find", "resend_product_found", "runtime_ids"] = "none"
    reason: str | None = None


class ReconciliationResult(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    resolved: bool = False
    crm_listing_id: str | None = None
    crm_product_id: str | None = None
    action: str | None = None
    source: Literal["response", "runtime", "catalog_find", "resend"] = "response"
    notes: list[str] = Field(default_factory=list)
