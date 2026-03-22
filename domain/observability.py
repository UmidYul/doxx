from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

SyncTraceStage = Literal[
    "crawl",
    "normalize",
    "lifecycle_select",
    "delivery_send",
    "crm_apply",
    "reconcile",
    "internal",
]

SyncSeverity = Literal["debug", "info", "warning", "error", "critical"]

FailureDomain = Literal[
    "crawl",
    "anti_bot",
    "parsing",
    "normalization",
    "lifecycle",
    "transport",
    "crm_apply",
    "reconciliation",
    "internal",
]

FailureType = Literal[
    "empty_listing",
    "block_page",
    "parse_failed",
    "partial_product",
    "low_mapping_coverage",
    "event_fallback",
    "timeout",
    "http_error",
    "malformed_response",
    "rejected_item",
    "retryable_item",
    "missing_ids",
    "ambiguous_result",
    "reconciliation_failed",
    "duplicate_payload_skipped",
]


class SyncCorrelationContext(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    run_id: str
    spider_name: str
    store_name: str
    category_url: str | None = None
    source_url: str | None = None
    source_id: str | None = None
    entity_key: str | None = None
    event_id: str | None = None
    payload_hash: str | None = None
    request_idempotency_key: str | None = None
    batch_id: str | None = None


class SyncTraceRecord(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    stage: SyncTraceStage
    severity: SyncSeverity
    message_code: str
    correlation: SyncCorrelationContext
    metrics: dict[str, object] = Field(default_factory=dict)
    details: dict[str, object] = Field(default_factory=dict)
    failure_domain: FailureDomain | None = None
    failure_type: FailureType | None = None

    @field_serializer("timestamp")
    def _ser_ts(self, v: datetime) -> str:
        if v.tzinfo is None:
            v = v.replace(tzinfo=UTC)
        return v.isoformat().replace("+00:00", "Z")


class BatchTraceRecord(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    batch_id: str
    run_id: str
    store_name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    flushed_at: datetime | None = None
    item_count: int = 0
    success_count: int = 0
    rejected_count: int = 0
    retryable_count: int = 0
    ignored_count: int = 0
    transport_failed: bool = False
    http_status: int | None = None
    notes: list[str] = Field(default_factory=list)

    @field_serializer("created_at", "flushed_at")
    def _ser_dt(self, v: datetime | None) -> str | None:
        if v is None:
            return None
        if v.tzinfo is None:
            v = v.replace(tzinfo=UTC)
        return v.isoformat().replace("+00:00", "Z")


class ParserHealthSnapshot(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    run_id: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    stores: list[str] = Field(default_factory=list)
    counters: dict[str, int | float] = Field(default_factory=dict)
    last_errors: list[dict[str, object]] = Field(default_factory=list)
    status: Literal["healthy", "degraded", "failing"] = "healthy"
    # --- 5B operational policy (SLO / thresholds / alerts); JSON-friendly dicts ---
    threshold_decisions: list[dict[str, object]] = Field(default_factory=list)
    operational_alerts: list[dict[str, object]] = Field(default_factory=list)
    dashboard_summary: dict[str, object] = Field(default_factory=dict)
    serialized_run_operational: dict[str, object] = Field(default_factory=dict)
    error_aggregates_by_domain: dict[str, dict[str, int]] = Field(default_factory=dict)
    # --- Operator support / triage / runbooks (5C): JSON-friendly bundle for export & tooling ---
    operator_support: dict[str, object] = Field(default_factory=dict)

    @field_serializer("started_at")
    def _ser_started(self, v: datetime) -> str:
        if v.tzinfo is None:
            v = v.replace(tzinfo=UTC)
        return v.isoformat().replace("+00:00", "Z")
