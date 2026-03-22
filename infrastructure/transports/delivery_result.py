from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SyncDeliveryResult:
    """Normalized outcome of one sync delivery (single item or batch row)."""

    success: bool
    retryable: bool
    http_status: int
    entity_key: str
    crm_listing_id: str | None = None
    crm_product_id: str | None = None
    action: str | None = None
    error_code: str | None = None
    error_message: str | None = None
