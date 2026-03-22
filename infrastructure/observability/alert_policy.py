from __future__ import annotations

from config.settings import settings
from domain.operational_policy import AlertSeverity, AlertSignal, IncidentDomain, ThresholdDecision

from infrastructure.observability.threshold_evaluator import (
    METRIC_APPLY_SUCCESS_RATE,
    METRIC_BLOCK_PAGE_RATE,
    METRIC_DUPLICATE_PAYLOAD_SKIP_RATE,
    METRIC_LOW_COVERAGE_RATE,
    METRIC_MALFORMED_RESPONSE_RATE,
    METRIC_MIN_ITEMS_PER_STORE,
    METRIC_PARSE_SUCCESS_RATE,
    METRIC_REJECTED_ITEM_RATE,
    METRIC_RETRYABLE_FAILURE_RATE,
    METRIC_UNRESOLVED_RECONCILIATION_RATE,
    METRIC_ZERO_RESULT_CATEGORY_RATE,
)


def classify_alert_domain(metric_name: str) -> IncidentDomain:
    if metric_name in (METRIC_BLOCK_PAGE_RATE, METRIC_ZERO_RESULT_CATEGORY_RATE):
        return "store_access"
    if metric_name == METRIC_PARSE_SUCCESS_RATE:
        return "crawl_quality"
    if metric_name == METRIC_LOW_COVERAGE_RATE:
        return "normalization_quality"
    if metric_name in (METRIC_APPLY_SUCCESS_RATE, METRIC_REJECTED_ITEM_RATE, METRIC_RETRYABLE_FAILURE_RATE):
        return "crm_apply"
    if metric_name == METRIC_MALFORMED_RESPONSE_RATE:
        return "delivery_transport"
    if metric_name == METRIC_UNRESOLVED_RECONCILIATION_RATE:
        return "reconciliation"
    if metric_name in (METRIC_DUPLICATE_PAYLOAD_SKIP_RATE, METRIC_MIN_ITEMS_PER_STORE):
        return "internal"
    return "internal"


def decide_alert_severity(metric_name: str, observed_value: float, threshold_value: float) -> AlertSeverity:
    """Refine severity from distance beyond SLO (on top of threshold breach)."""
    if metric_name in (METRIC_BLOCK_PAGE_RATE, METRIC_MALFORMED_RESPONSE_RATE, METRIC_UNRESOLVED_RECONCILIATION_RATE):
        gap = abs(observed_value - threshold_value)
        if gap > 0.15 or observed_value > threshold_value * 3:
            return "critical"
        if gap > 0.05:
            return "high"
        return "warning"

    if metric_name == METRIC_LOW_COVERAGE_RATE or metric_name == METRIC_DUPLICATE_PAYLOAD_SKIP_RATE:
        gap = abs(observed_value - threshold_value)
        if metric_name == METRIC_DUPLICATE_PAYLOAD_SKIP_RATE and observed_value > 0.85:
            return "high"
        if gap > 0.25:
            return "warning"
        return "info"

    if metric_name in (METRIC_PARSE_SUCCESS_RATE, METRIC_APPLY_SUCCESS_RATE):
        shortfall = threshold_value - observed_value
        if shortfall > 0.15:
            return "critical"
        if shortfall > 0.08:
            return "high"
        return "warning"

    if metric_name == METRIC_REJECTED_ITEM_RATE:
        excess = observed_value - threshold_value
        if excess > 0.2:
            return "critical"
        if excess > 0.08:
            return "high"
        return "warning"

    if metric_name == METRIC_RETRYABLE_FAILURE_RATE:
        excess = observed_value - threshold_value
        if excess > 0.15:
            return "high"
        return "warning"

    if metric_name == METRIC_ZERO_RESULT_CATEGORY_RATE:
        excess = observed_value - threshold_value
        if excess > 0.25:
            return "high"
        return "warning"

    return "warning"


def build_alerts_from_thresholds(
    run_id: str,
    store_name: str | None,
    decisions: list[ThresholdDecision],
) -> list[AlertSignal]:
    alerts: list[AlertSignal] = []
    for d in decisions:
        if not d.breached:
            continue
        domain = classify_alert_domain(d.metric_name)
        sev = decide_alert_severity(d.metric_name, d.observed_value, d.threshold_value)
        base = d.severity
        if base:
            sev = _max_severity(sev, base)
        code = f"THRESHOLD_BREACHED:{d.metric_name}"
        msg = (
            f"{d.metric_name} breached SLO (observed={d.observed_value:.4f}, "
            f"threshold={d.threshold_value:.4f}, cmp={d.comparator})"
        )
        alerts.append(
            AlertSignal(
                alert_code=code,
                severity=sev,
                domain=domain,
                store_name=store_name,
                run_id=run_id,
                metric_name=d.metric_name,
                observed_value=d.observed_value,
                threshold_value=d.threshold_value,
                message=msg,
                tags={"comparator": d.comparator},
            )
        )
    _ = settings  # reserved for future per-tenant tuning
    return alerts


def _max_severity(a: AlertSeverity, b: AlertSeverity) -> AlertSeverity:
    order = ("info", "warning", "high", "critical")
    ia = order.index(a) if a in order else 1
    ib = order.index(b) if b in order else 1
    return a if ia >= ib else b
