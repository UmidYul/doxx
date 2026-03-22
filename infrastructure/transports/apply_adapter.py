from __future__ import annotations

from domain.crm_apply_result import CrmApplyResult
from infrastructure.transports.delivery_result import SyncDeliveryResult


def crm_apply_to_sync_delivery(r: CrmApplyResult) -> SyncDeliveryResult:
    """Backward-compat shim for code expecting :class:`SyncDeliveryResult`."""
    return SyncDeliveryResult(
        success=r.success,
        retryable=r.retryable,
        http_status=r.http_status or 0,
        entity_key=r.entity_key,
        crm_listing_id=r.crm_listing_id,
        crm_product_id=r.crm_product_id,
        action=r.action,
        error_code=r.error_code,
        error_message=r.error_message,
    )
