from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PerformanceStage = Literal[
    "crawl_request",
    "listing_parse",
    "product_parse",
    "normalize",
    "lifecycle_build",
    "batch_buffer",
    "crm_send",
    "crm_apply_parse",
    "reconcile",
    "observability",
]


class StageTimingRecord(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    stage: PerformanceStage
    started_at: datetime
    finished_at: datetime
    duration_ms: float
    store_name: str | None = None
    spider_name: str | None = None
    entity_key: str | None = None
    batch_id: str | None = None
    notes: list[str] = Field(default_factory=list)


class StorePerformanceSnapshot(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    store_name: str
    requests_total: int = 0
    products_total: int = 0
    batches_total: int = 0
    avg_request_ms: float | None = None
    avg_product_parse_ms: float | None = None
    avg_normalize_ms: float | None = None
    avg_crm_send_ms: float | None = None
    avg_batch_apply_ms: float | None = None
    products_per_minute: float | None = None
    batches_per_minute: float | None = None
    memory_estimate_mb: float | None = None
    status: Literal["normal", "slow", "critical"] = "normal"


class RunPerformanceSnapshot(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    run_id: str
    started_at: datetime
    stores: list[str] = Field(default_factory=list)
    stage_averages_ms: dict[str, float] = Field(default_factory=dict)
    store_snapshots: list[StorePerformanceSnapshot] = Field(default_factory=list)
    slowest_stages: list[str] = Field(default_factory=list)
    bottlenecks: list[str] = Field(default_factory=list)
    overall_status: Literal["normal", "slow", "critical"] = "normal"


class BottleneckSignal(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    stage: PerformanceStage
    store_name: str | None = None
    severity: Literal["warning", "high", "critical"]
    observed_ms: float
    threshold_ms: float
    reason: str


def utcnow() -> datetime:
    return datetime.now(UTC)
