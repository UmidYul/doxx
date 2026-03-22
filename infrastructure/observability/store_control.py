from __future__ import annotations

from typing import Literal

from config.settings import settings
from domain.operational_policy import RunOperationalStatus, StoreOperationalStatus

from infrastructure.observability.incident_classifier import (
    classify_run_incident,
    classify_store_incident,
    should_disable_store,
    should_fail_run,
)


def suggest_store_action(status: StoreOperationalStatus) -> Literal["continue", "degrade", "disable_store"]:
    if status.status == "failing":
        if should_disable_store(status):
            return "disable_store"
        return "degrade"
    if status.status == "degraded":
        return "degrade"
    return "continue"


def suggest_run_action(status: RunOperationalStatus) -> Literal["continue", "degrade", "fail_run"]:
    if should_fail_run(status):
        return "fail_run"
    if status.status == "failing":
        return "degrade"
    if status.status == "degraded":
        return "degrade"
    return "continue"


def explain_store_action(status: StoreOperationalStatus) -> list[str]:
    lines: list[str] = []
    dom = classify_store_incident(status)
    lines.append(f"store_status={status.status}")
    lines.append(f"primary_incident_domain={dom}")
    lines.append(f"breached_thresholds={len([d for d in status.breached_thresholds if d.breached])}")
    lines.append(f"critical_alerts={sum(1 for a in status.alerts if a.severity == 'critical')}")
    if should_disable_store(status) and settings.INCIDENT_DISABLE_STORE_ON_CRITICAL_STORE_ALERT:
        lines.append("policy_allows_store_disable_on_critical=true")
    else:
        lines.append("store_disable_is_advisory_only=true")
    return lines


def explain_run_action(status: RunOperationalStatus) -> list[str]:
    lines: list[str] = []
    lines.append(f"run_status={status.status}")
    lines.append(f"run_incident_domain={classify_run_incident(status)}")
    lines.append(f"global_alerts={len(status.global_alerts)}")
    if should_fail_run(status) and settings.INCIDENT_FAIL_RUN_ON_CRITICAL_GLOBAL_ALERT:
        lines.append("policy_allows_fail_run_on_global_critical=true")
    else:
        lines.append("fail_run_is_advisory_only=true")
    return lines
