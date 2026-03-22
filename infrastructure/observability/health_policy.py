from __future__ import annotations

from typing import Literal

from domain.observability import SyncTraceRecord
from domain.operational_policy import ServiceStatus

from infrastructure.observability.metrics_collector import (
    BLOCK_PAGES_TOTAL,
    CRM_REJECTED_TOTAL,
    CRM_RETRYABLE_TOTAL,
    CRAWL_FAILURES_TOTAL,
    DELIVERY_RETRIES_TOTAL,
    DUPLICATE_PAYLOAD_SKIPPED_TOTAL,
    NORMALIZATION_LOW_COVERAGE_TOTAL,
    RECONCILIATION_FAILED_TOTAL,
    get_observability_metrics,
)


def worst_service_status(a: ServiceStatus, b: ServiceStatus) -> ServiceStatus:
    order = ("healthy", "degraded", "failing")
    return a if order.index(a) >= order.index(b) else b


def compute_parser_health(
    counters: dict[str, int | float],
    recent_failures: list[SyncTraceRecord],
) -> Literal["healthy", "degraded", "failing"]:
    """
    Derive aggregate parser health for operator dashboards.
    Uses counters + recent high-severity trace records.
    """
    tf = float(counters.get("transport_failures_total", 0) or counters.get("batch_transport_failures_total", 0))
    if tf == 0:
        # Also read from observability metrics if sync used legacy names
        snap = get_observability_metrics().snapshot()
        # delivery retries proxy transport stress
        tf = float(snap.get("delivery_retries_total", 0))

    rejected = float(counters.get(CRM_REJECTED_TOTAL, 0))
    retryable = float(counters.get(CRM_RETRYABLE_TOTAL, 0))
    block_pages = float(counters.get(BLOCK_PAGES_TOTAL, 0))
    crawl_failures = float(counters.get(CRAWL_FAILURES_TOTAL, 0))
    low_cov = float(counters.get(NORMALIZATION_LOW_COVERAGE_TOTAL, 0))
    malformed = sum(
        1
        for r in recent_failures
        if r.failure_type == "malformed_response" or str(r.message_code).endswith("MALFORMED")
    )
    unreconciled = sum(
        1
        for r in recent_failures
        if r.message_code == "RECONCILIATION_UNRESOLVED" or r.failure_type == "reconciliation_failed"
    )
    recon_failed_ctr = float(counters.get(RECONCILIATION_FAILED_TOTAL, 0))

    crit = sum(1 for r in recent_failures if r.severity == "critical")
    err = sum(1 for r in recent_failures if r.severity == "error")

    failing_signals = 0
    if crit >= 1:
        failing_signals += 2
    if malformed >= 2 or recon_failed_ctr >= 3:
        failing_signals += 2
    if tf >= 5 and rejected >= 5:
        failing_signals += 2

    degraded_signals = 0
    if err >= 5 or retryable >= 10:
        degraded_signals += 1
    if block_pages >= 3 or crawl_failures >= 20:
        degraded_signals += 1
    if low_cov >= 15:
        degraded_signals += 1
    if float(counters.get(DUPLICATE_PAYLOAD_SKIPPED_TOTAL, 0)) >= 50:
        degraded_signals += 1
    if float(counters.get(DELIVERY_RETRIES_TOTAL, 0)) >= 15:
        degraded_signals += 1
    if unreconciled >= 3:
        degraded_signals += 1

    for r in recent_failures[-50:]:
        if r.failure_type == "block_page":
            degraded_signals += 1

    if failing_signals >= 2:
        return "failing"
    if failing_signals >= 1 or degraded_signals >= 2:
        return "degraded"
    return "healthy"


def merge_health_with_operational(
    heuristic_status: Literal["healthy", "degraded", "failing"],
    operational_status: ServiceStatus,
) -> Literal["healthy", "degraded", "failing"]:
    """Combine 5A heuristic health with 5B SLO-derived status (worst wins)."""
    return worst_service_status(heuristic_status, operational_status)
