from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CostDriver = Literal[
    "http_requests",
    "proxy_requests",
    "browser_pages",
    "retry_attempts",
    "batch_flushes",
    "crm_roundtrips",
    "normalization_cpu",
    "diagnostic_overhead",
]

CostEfficiencyStatus = Literal["efficient", "acceptable", "expensive", "critical"]


class StoreCostSnapshot(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    store_name: str
    http_requests: int = 0
    proxy_requests: int = 0
    browser_pages: int = 0
    retry_attempts: int = 0
    batch_flushes: int = 0
    crm_roundtrips: int = 0
    products_parsed: int = 0
    products_applied: int = 0
    estimated_cost_units: float = 0.0
    products_per_cost_unit: float | None = None
    applied_per_cost_unit: float | None = None
    status: CostEfficiencyStatus = "acceptable"


class RunCostSnapshot(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    run_id: str
    store_snapshots: list[StoreCostSnapshot] = Field(default_factory=list)
    total_estimated_cost_units: float = 0.0
    highest_cost_stores: list[str] = Field(default_factory=list)
    lowest_efficiency_stores: list[str] = Field(default_factory=list)
    overall_status: CostEfficiencyStatus = "acceptable"


class EfficiencySignal(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    store_name: str | None = None
    severity: Literal["warning", "high", "critical"]
    signal_code: str
    observed_value: float
    threshold_value: float
    reason: str


class CostRegressionResult(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    passed: bool
    metric_name: str
    baseline_value: float
    current_value: float
    allowed_delta_pct: float
    regression_pct: float
    reason: str
