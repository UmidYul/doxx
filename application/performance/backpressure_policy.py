from __future__ import annotations

from typing import Any

from config.settings import settings
from domain.resource_governance import (
    BackpressureDecision,
    ResourceMode,
    ResourceThrottleDecision,
    RuntimeResourceState,
    StoreResourceBudget,
)


def decide_backpressure(
    store_name: str,
    state: RuntimeResourceState,
    budget: StoreResourceBudget,
    settings_obj: Any | None = None,
) -> BackpressureDecision:
    """Signal backpressure from memory, retry queue, and batch inflight (advisory)."""
    st = (store_name or "").strip() or "unknown"
    s = settings_obj or settings
    if not getattr(s, "ENABLE_BACKPRESSURE_POLICY", True):
        return BackpressureDecision(
            apply_backpressure=False,
            store_name=st,
            reason="backpressure_disabled",
            severity="warning",
            suggested_action="slow_down",
        )

    mem = state.memory_mb
    mem_crit = float(getattr(s, "BACKPRESSURE_MEMORY_CRITICAL_MB", 512))
    mem_warn = float(getattr(s, "BACKPRESSURE_MEMORY_WARNING_MB", 384))
    gmem = float(getattr(s, "GLOBAL_MAX_MEMORY_MB", 512))

    if mem is not None and mem >= min(mem_crit, gmem):
        return BackpressureDecision(
            apply_backpressure=True,
            store_name=st,
            reason="memory_critical",
            severity="critical",
            suggested_action="degrade_store",
        )

    rq_crit = int(getattr(s, "BACKPRESSURE_RETRYABLE_QUEUE_CRITICAL", 200))
    rq_warn = int(getattr(s, "BACKPRESSURE_RETRYABLE_QUEUE_WARNING", 100))
    if state.queued_retryable_items >= min(rq_crit, budget.max_retryable_queue):
        return BackpressureDecision(
            apply_backpressure=True,
            store_name=st,
            reason="retryable_queue_critical",
            severity="critical",
            suggested_action="pause_batches",
        )
    if state.queued_retryable_items >= rq_warn:
        return BackpressureDecision(
            apply_backpressure=True,
            store_name=st,
            reason="retryable_queue_elevated",
            severity="high",
            suggested_action="slow_down",
        )

    bi_crit = int(getattr(s, "BACKPRESSURE_BATCH_INFLIGHT_CRITICAL", 4))
    bi_warn = int(getattr(s, "BACKPRESSURE_BATCH_INFLIGHT_WARNING", 3))
    if state.inflight_batches >= bi_crit:
        return BackpressureDecision(
            apply_backpressure=True,
            store_name=st,
            reason="batch_inflight_critical",
            severity="critical",
            suggested_action="pause_batches",
        )
    if state.inflight_batches >= bi_warn:
        return BackpressureDecision(
            apply_backpressure=True,
            store_name=st,
            reason="batch_inflight_elevated",
            severity="warning",
            suggested_action="slow_down",
        )

    if mem is not None and mem >= mem_warn:
        return BackpressureDecision(
            apply_backpressure=True,
            store_name=st,
            reason="memory_warning",
            severity="warning",
            suggested_action="reduce_browser",
        )

    return BackpressureDecision(
        apply_backpressure=False,
        store_name=st,
        reason="nominal",
        severity="warning",
        suggested_action="slow_down",
    )


def decide_throttle_adjustment(
    store_name: str,
    state: RuntimeResourceState,
    budget: StoreResourceBudget,
    settings_obj: Any | None = None,
) -> ResourceThrottleDecision:
    """Suggest a lower effective limit for browser/proxy when saturated (advisory)."""
    st = (store_name or "").strip() or "unknown"
    s = settings_obj or settings
    if not getattr(s, "ENABLE_RESOURCE_GOVERNANCE", True):
        return ResourceThrottleDecision(
            throttle=False,
            store_name=st,
            mode="http",
            new_limit=None,
            reason="governance_disabled",
        )

    g_b = int(getattr(s, "GLOBAL_MAX_BROWSER_PAGES", 2))
    if state.active_browser_pages >= min(budget.max_browser_pages, g_b):
        return ResourceThrottleDecision(
            throttle=True,
            store_name=st,
            mode="browser",
            new_limit=max(0, min(budget.max_browser_pages, g_b) - 1),
            reason="browser_pages_saturated",
        )

    g_p = int(getattr(s, "GLOBAL_MAX_PROXY_REQUESTS", 8))
    if state.active_proxy_requests >= min(budget.max_proxy_requests, g_p):
        return ResourceThrottleDecision(
            throttle=True,
            store_name=st,
            mode="proxy",
            new_limit=max(0, min(budget.max_proxy_requests, g_p) - 1),
            reason="proxy_requests_saturated",
        )

    return ResourceThrottleDecision(
        throttle=False,
        store_name=st,
        mode="http",
        new_limit=None,
        reason="no_throttle",
    )
