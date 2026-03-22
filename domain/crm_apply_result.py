from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CrmApplyStatus = Literal[
    "applied",
    "matched",
    "created",
    "updated",
    "ignored",
    "rejected",
    "retryable_failure",
    "transport_failure",
]


class CrmApplyResult(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    event_id: str
    entity_key: str
    payload_hash: str
    success: bool
    status: CrmApplyStatus
    http_status: int | None = None
    action: str | None = None
    crm_listing_id: str | None = None
    crm_product_id: str | None = None
    retryable: bool = False
    error_code: str | None = None
    error_message: str | None = None
    # --- 4C parser-side reconciliation hints (CRM may still return HTTP 2xx) ---
    parser_reconciliation_signal: str | None = None  # missing_ids | ambiguous_action | response_lost


class CrmBatchApplyResult(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    items: list[CrmApplyResult] = Field(default_factory=list)
    transport_ok: bool = True
    http_status: int | None = None
    batch_error_code: str | None = None
    batch_error_message: str | None = None


class CrmBatchSummary(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    total: int = 0
    succeeded: int = 0
    failed: int = 0
    retryable_failed: int = 0
    rejected: int = 0
    ignored: int = 0


def summarize_batch_result(batch: CrmBatchApplyResult) -> CrmBatchSummary:
    items = batch.items or []
    total = len(items)
    succeeded = sum(1 for i in items if i.success)
    failed = total - succeeded
    retryable_failed = sum(1 for i in items if (not i.success) and i.retryable)
    rejected = sum(1 for i in items if i.status == "rejected")
    ignored = sum(1 for i in items if i.status == "ignored")
    return CrmBatchSummary(
        total=total,
        succeeded=succeeded,
        failed=failed,
        retryable_failed=retryable_failed,
        rejected=rejected,
        ignored=ignored,
    )


class MalformedCrmBatchResponse(Exception):
    """Raised when batch JSON does not satisfy CRM_BATCH_REQUIRE_ITEM_RESULTS (optional)."""

    def __init__(self, message: str, *, batch: CrmBatchApplyResult | None = None) -> None:
        super().__init__(message)
        self.batch = batch
