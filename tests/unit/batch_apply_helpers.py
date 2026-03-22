"""Shared builders for 4B CRM batch/apply unit tests."""

from __future__ import annotations

from domain.crm_apply_result import CrmApplyResult, CrmApplyStatus, CrmBatchApplyResult
from domain.parser_event import ParserSyncEvent


def crm_apply_ok(
    event: ParserSyncEvent,
    *,
    crm_listing_id: str = "l1",
    crm_product_id: str = "p1",
    action: str = "created",
    status: CrmApplyStatus = "created",
) -> CrmApplyResult:
    return CrmApplyResult(
        event_id=event.event_id,
        entity_key=event.data.entity_key,
        payload_hash=event.data.payload_hash,
        success=True,
        status=status,
        http_status=200,
        action=action,
        crm_listing_id=crm_listing_id,
        crm_product_id=crm_product_id,
    )


def crm_apply_fail(
    event: ParserSyncEvent,
    *,
    retryable: bool,
    status: CrmApplyStatus = "rejected",
    http_status: int = 200,
    error_message: str = "biz",
) -> CrmApplyResult:
    return CrmApplyResult(
        event_id=event.event_id,
        entity_key=event.data.entity_key,
        payload_hash=event.data.payload_hash,
        success=False,
        status=status,
        http_status=http_status,
        retryable=retryable,
        error_message=error_message,
    )


def batch_mirror_success(events: list[ParserSyncEvent]) -> CrmBatchApplyResult:
    return CrmBatchApplyResult(
        items=[crm_apply_ok(e) for e in events],
        transport_ok=True,
        http_status=200,
    )
