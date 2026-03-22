from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ServiceStatus = Literal["healthy", "degraded", "failing"]

AlertSeverity = Literal["info", "warning", "high", "critical"]

IncidentDomain = Literal[
    "store_access",
    "crawl_quality",
    "normalization_quality",
    "delivery_transport",
    "crm_apply",
    "reconciliation",
    "internal",
]


class ThresholdDecision(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    metric_name: str
    observed_value: float
    threshold_value: float
    comparator: str
    breached: bool
    severity: AlertSeverity | None = None
    notes: list[str] = Field(default_factory=list)


class AlertSignal(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    alert_code: str
    severity: AlertSeverity
    domain: IncidentDomain
    store_name: str | None = None
    run_id: str
    metric_name: str | None = None
    observed_value: float | None = None
    threshold_value: float | None = None
    message: str
    tags: dict[str, str] = Field(default_factory=dict)


class StoreOperationalStatus(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    store_name: str
    status: ServiceStatus
    alerts: list[AlertSignal] = Field(default_factory=list)
    breached_thresholds: list[ThresholdDecision] = Field(default_factory=list)
    counters: dict[str, int | float] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class RunOperationalStatus(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    run_id: str
    status: ServiceStatus
    store_statuses: list[StoreOperationalStatus] = Field(default_factory=list)
    global_alerts: list[AlertSignal] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
