from __future__ import annotations

import threading
from typing import Any

# Standardized counter names for parser → CRM observability (5A).
CRAWL_LISTING_PAGES_TOTAL = "crawl_listing_pages_total"
CRAWL_PRODUCT_PAGES_TOTAL = "crawl_product_pages_total"
CRAWL_PARTIAL_PRODUCTS_TOTAL = "crawl_partial_products_total"
CRAWL_FAILURES_TOTAL = "crawl_failures_total"
NORMALIZATION_ITEMS_TOTAL = "normalization_items_total"
NORMALIZATION_LOW_COVERAGE_TOTAL = "normalization_low_coverage_total"
LIFECYCLE_FALLBACKS_TOTAL = "lifecycle_fallbacks_total"
DELIVERY_BATCHES_TOTAL = "delivery_batches_total"
DELIVERY_ITEMS_TOTAL = "delivery_items_total"
DELIVERY_RETRIES_TOTAL = "delivery_retries_total"
CRM_APPLIED_TOTAL = "crm_applied_total"
CRM_REJECTED_TOTAL = "crm_rejected_total"
CRM_RETRYABLE_TOTAL = "crm_retryable_total"
CRM_IGNORED_TOTAL = "crm_ignored_total"
RECONCILIATION_STARTED_TOTAL = "reconciliation_started_total"
RECONCILIATION_RESOLVED_TOTAL = "reconciliation_resolved_total"
RECONCILIATION_FAILED_TOTAL = "reconciliation_failed_total"
DUPLICATE_PAYLOAD_SKIPPED_TOTAL = "duplicate_payload_skipped_total"
BLOCK_PAGES_TOTAL = "block_pages_total"
PUBLISHER_CONNECT_FAILURES_TOTAL = "publisher_connect_failures_total"
PUBLISHER_PUBLISH_RETRIES_TOTAL = "publisher_publish_retries_total"
PUBLISHER_MESSAGE_FAILURES_TOTAL = "publisher_message_failures_total"
PUBLISHER_BATCHES_TOTAL = "publisher_batches_total"
PUBLISHER_RUN_FAILURES_TOTAL = "publisher_run_failures_total"
PUBLISHER_SMOKE_RUNS_TOTAL = "publisher_smoke_runs_total"
PUBLISHER_SMOKE_FAILURES_TOTAL = "publisher_smoke_failures_total"

_ALL_KEYS: tuple[str, ...] = (
    CRAWL_LISTING_PAGES_TOTAL,
    CRAWL_PRODUCT_PAGES_TOTAL,
    CRAWL_PARTIAL_PRODUCTS_TOTAL,
    CRAWL_FAILURES_TOTAL,
    NORMALIZATION_ITEMS_TOTAL,
    NORMALIZATION_LOW_COVERAGE_TOTAL,
    LIFECYCLE_FALLBACKS_TOTAL,
    DELIVERY_BATCHES_TOTAL,
    DELIVERY_ITEMS_TOTAL,
    DELIVERY_RETRIES_TOTAL,
    CRM_APPLIED_TOTAL,
    CRM_REJECTED_TOTAL,
    CRM_RETRYABLE_TOTAL,
    CRM_IGNORED_TOTAL,
    RECONCILIATION_STARTED_TOTAL,
    RECONCILIATION_RESOLVED_TOTAL,
    RECONCILIATION_FAILED_TOTAL,
    DUPLICATE_PAYLOAD_SKIPPED_TOTAL,
    BLOCK_PAGES_TOTAL,
    PUBLISHER_CONNECT_FAILURES_TOTAL,
    PUBLISHER_PUBLISH_RETRIES_TOTAL,
    PUBLISHER_MESSAGE_FAILURES_TOTAL,
    PUBLISHER_BATCHES_TOTAL,
    PUBLISHER_RUN_FAILURES_TOTAL,
    PUBLISHER_SMOKE_RUNS_TOTAL,
    PUBLISHER_SMOKE_FAILURES_TOTAL,
)


class ObservabilityMetricsCollector:
    """Thread-safe in-process counters for diagnostics (no external TSDB)."""

    __slots__ = ("_lock", "_counters")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, float] = {k: 0.0 for k in _ALL_KEYS}

    def inc(self, name: str, delta: float = 1.0) -> None:
        if name not in self._counters:
            with self._lock:
                self._counters.setdefault(name, 0.0)
        with self._lock:
            self._counters[name] = float(self._counters.get(name, 0.0)) + float(delta)

    def snapshot(self) -> dict[str, int | float]:
        with self._lock:
            return dict(self._counters)

    def reset(self) -> None:
        with self._lock:
            for k in self._counters:
                self._counters[k] = 0.0


_metrics_singleton: ObservabilityMetricsCollector | None = None
_metrics_lock = threading.Lock()


def get_observability_metrics() -> ObservabilityMetricsCollector:
    global _metrics_singleton
    with _metrics_lock:
        if _metrics_singleton is None:
            _metrics_singleton = ObservabilityMetricsCollector()
        return _metrics_singleton


def reset_observability_metrics_for_tests() -> None:
    global _metrics_singleton
    with _metrics_lock:
        if _metrics_singleton is not None:
            _metrics_singleton.reset()


def bump_counter_for_message_code(code: str) -> None:
    """Map stable message codes to standardized counters (best-effort)."""
    from infrastructure.observability import message_codes as mc

    m = get_observability_metrics()
    match code:
        case mc.CRAWL_LISTING_SEEN:
            m.inc(CRAWL_LISTING_PAGES_TOTAL)
        case mc.CRAWL_PRODUCT_PARSED:
            m.inc(CRAWL_PRODUCT_PAGES_TOTAL)
        case mc.CRAWL_PRODUCT_PARTIAL:
            m.inc(CRAWL_PARTIAL_PRODUCTS_TOTAL)
        case mc.CRAWL_FAILURE:
            m.inc(CRAWL_FAILURES_TOTAL)
        case mc.NORMALIZATION_COMPLETED:
            m.inc(NORMALIZATION_ITEMS_TOTAL)
        case mc.NORMALIZATION_LOW_COVERAGE:
            m.inc(NORMALIZATION_LOW_COVERAGE_TOTAL)
        case mc.LIFECYCLE_FALLBACK_APPLIED:
            m.inc(LIFECYCLE_FALLBACKS_TOTAL)
        case mc.DELIVERY_BATCH_STARTED:
            m.inc(DELIVERY_BATCHES_TOTAL)
        case mc.DELIVERY_BATCH_COMPLETED:
            pass
        case mc.CRM_IDS_PROPAGATED:
            pass
        case mc.CRM_APPLY_IGNORED:
            m.inc(CRM_IGNORED_TOTAL)
        case mc.DELIVERY_RETRY:
            m.inc(DELIVERY_RETRIES_TOTAL)
        case mc.CRM_APPLY_SUCCESS:
            m.inc(CRM_APPLIED_TOTAL)
        case mc.CRM_APPLY_REJECTED:
            m.inc(CRM_REJECTED_TOTAL)
        case mc.CRM_APPLY_RETRYABLE:
            m.inc(CRM_RETRYABLE_TOTAL)
        case mc.RECONCILIATION_STARTED:
            m.inc(RECONCILIATION_STARTED_TOTAL)
        case mc.RECONCILIATION_RESOLVED:
            m.inc(RECONCILIATION_RESOLVED_TOTAL)
        case mc.RECONCILIATION_UNRESOLVED:
            m.inc(RECONCILIATION_FAILED_TOTAL)
        case mc.DUPLICATE_PAYLOAD_SKIPPED:
            m.inc(DUPLICATE_PAYLOAD_SKIPPED_TOTAL)
        case mc.HEALTH_STATUS_CHANGED:
            pass
        case mc.PUBLISHER_CONNECT_FAILED:
            m.inc(PUBLISHER_CONNECT_FAILURES_TOTAL)
        case mc.PUBLISHER_PUBLISH_RETRY:
            m.inc(PUBLISHER_PUBLISH_RETRIES_TOTAL)
        case mc.PUBLISHER_MESSAGE_FAILED:
            m.inc(PUBLISHER_MESSAGE_FAILURES_TOTAL)
        case mc.PUBLISHER_BATCH_COMPLETED:
            m.inc(PUBLISHER_BATCHES_TOTAL)
        case mc.PUBLISHER_RUN_FAILED:
            m.inc(PUBLISHER_RUN_FAILURES_TOTAL)
        case mc.PUBLISHER_SMOKE_COMPLETED:
            m.inc(PUBLISHER_SMOKE_RUNS_TOTAL)
        case mc.PUBLISHER_SMOKE_FAILED:
            m.inc(PUBLISHER_SMOKE_FAILURES_TOTAL)
        case _:
            pass


# Alias for typing
MetricsSnapshot = dict[str, Any]
