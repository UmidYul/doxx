from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ResourceMode = Literal["http", "proxy", "browser"]


class StoreResourceBudget(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    store_name: str
    max_concurrent_requests: int = Field(ge=0)
    max_listing_requests: int = Field(ge=0)
    max_product_requests: int = Field(ge=0)
    max_batch_inflight: int = Field(ge=0)
    max_retryable_queue: int = Field(ge=0)
    max_browser_pages: int = Field(ge=0)
    max_proxy_requests: int = Field(ge=0)
    max_memory_mb: int | None = Field(default=None, ge=0)
    notes: list[str] = Field(default_factory=list)


class RuntimeResourceState(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    store_name: str
    inflight_requests: int = 0
    inflight_listing_requests: int = 0
    inflight_product_requests: int = 0
    inflight_batches: int = 0
    queued_retryable_items: int = 0
    active_browser_pages: int = 0
    active_proxy_requests: int = 0
    memory_mb: float | None = None


class ConcurrencyDecision(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    allowed: bool
    store_name: str
    reason: str
    selected_limit: int
    mode: ResourceMode


class BackpressureDecision(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    apply_backpressure: bool
    store_name: str
    reason: str
    severity: Literal["warning", "high", "critical"]
    suggested_action: Literal[
        "slow_down",
        "pause_batches",
        "reduce_browser",
        "reduce_proxy",
        "degrade_store",
    ]


class ResourceThrottleDecision(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    throttle: bool
    store_name: str
    mode: ResourceMode
    new_limit: int | None = None
    reason: str
