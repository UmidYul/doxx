from __future__ import annotations

from typing import Any, Literal

from config.settings import settings
from domain.resource_governance import (
    ConcurrencyDecision,
    ResourceMode,
    RuntimeResourceState,
    StoreResourceBudget,
)
from infrastructure.performance.resource_tracker import (
    get_global_browser_pages_total,
    get_global_inflight_batches_total,
    get_global_inflight_requests_total,
    get_global_proxy_requests_total,
)


def _cap(a: int, b: int) -> int:
    return max(0, min(int(a), int(b)))


def decide_request_admission(
    store_name: str,
    purpose: Literal["listing", "product"],
    mode: ResourceMode,
    state: RuntimeResourceState,
    budget: StoreResourceBudget,
) -> ConcurrencyDecision:
    """Enforce global + per-store concurrent request limits and retry-queue pressure."""
    st = (store_name or "").strip() or "unknown"
    if not getattr(settings, "ENABLE_RESOURCE_GOVERNANCE", True):
        return ConcurrencyDecision(
            allowed=True,
            store_name=st,
            reason="governance_disabled",
            selected_limit=int(budget.max_concurrent_requests),
            mode=mode,
        )

    g_total = int(getattr(settings, "GLOBAL_MAX_CONCURRENT_REQUESTS", 16))
    g_rq = int(getattr(settings, "GLOBAL_MAX_RETRYABLE_QUEUE", 200))
    crit_rq = int(getattr(settings, "BACKPRESSURE_RETRYABLE_QUEUE_CRITICAL", 200))

    if state.queued_retryable_items >= min(crit_rq, g_rq, budget.max_retryable_queue):
        return ConcurrencyDecision(
            allowed=False,
            store_name=st,
            reason="retryable_queue_pressure_blocks_new_requests",
            selected_limit=0,
            mode=mode,
        )

    if get_global_inflight_requests_total() >= g_total:
        return ConcurrencyDecision(
            allowed=False,
            store_name=st,
            reason="global_concurrent_request_cap",
            selected_limit=g_total,
            mode=mode,
        )

    cap_all = _cap(budget.max_concurrent_requests, g_total)
    if state.inflight_requests >= cap_all:
        return ConcurrencyDecision(
            allowed=False,
            store_name=st,
            reason="store_concurrent_request_cap",
            selected_limit=cap_all,
            mode=mode,
        )

    if purpose == "listing":
        lim = _cap(budget.max_listing_requests, cap_all)
        if state.inflight_listing_requests >= lim:
            return ConcurrencyDecision(
                allowed=False,
                store_name=st,
                reason="store_listing_concurrent_cap",
                selected_limit=lim,
                mode=mode,
            )
    else:
        lim = _cap(budget.max_product_requests, cap_all)
        if state.inflight_product_requests >= lim:
            return ConcurrencyDecision(
                allowed=False,
                store_name=st,
                reason="store_product_concurrent_cap",
                selected_limit=lim,
                mode=mode,
            )

    br = decide_browser_admission(st, state, budget)
    pr = decide_proxy_admission(st, state, budget)
    if mode == "browser" and not br.allowed:
        return br
    if mode == "proxy" and not pr.allowed:
        return pr

    return ConcurrencyDecision(
        allowed=True,
        store_name=st,
        reason="admitted",
        selected_limit=cap_all,
        mode=mode,
    )


def decide_browser_admission(
    store_name: str,
    state: RuntimeResourceState,
    budget: StoreResourceBudget,
) -> ConcurrencyDecision:
    st = (store_name or "").strip() or "unknown"
    if not getattr(settings, "ENABLE_RESOURCE_GOVERNANCE", True) or not getattr(
        settings, "ENABLE_BROWSER_BUDGETS", True
    ):
        return ConcurrencyDecision(
            allowed=True,
            store_name=st,
            reason="browser_budgets_disabled",
            selected_limit=budget.max_browser_pages,
            mode="browser",
        )
    g = int(getattr(settings, "GLOBAL_MAX_BROWSER_PAGES", 2))
    cap = _cap(budget.max_browser_pages, g)
    if get_global_browser_pages_total() >= g:
        return ConcurrencyDecision(
            allowed=False,
            store_name=st,
            reason="global_browser_pages_cap",
            selected_limit=g,
            mode="browser",
        )
    if state.active_browser_pages >= cap:
        return ConcurrencyDecision(
            allowed=False,
            store_name=st,
            reason="store_browser_pages_cap",
            selected_limit=cap,
            mode="browser",
        )
    return ConcurrencyDecision(
        allowed=True,
        store_name=st,
        reason="browser_admitted",
        selected_limit=cap,
        mode="browser",
    )


def decide_proxy_admission(
    store_name: str,
    state: RuntimeResourceState,
    budget: StoreResourceBudget,
) -> ConcurrencyDecision:
    st = (store_name or "").strip() or "unknown"
    if not getattr(settings, "ENABLE_RESOURCE_GOVERNANCE", True) or not getattr(
        settings, "ENABLE_PROXY_BUDGETS", True
    ):
        return ConcurrencyDecision(
            allowed=True,
            store_name=st,
            reason="proxy_budgets_disabled",
            selected_limit=budget.max_proxy_requests,
            mode="proxy",
        )
    g = int(getattr(settings, "GLOBAL_MAX_PROXY_REQUESTS", 8))
    cap = _cap(budget.max_proxy_requests, g)
    if get_global_proxy_requests_total() >= g:
        return ConcurrencyDecision(
            allowed=False,
            store_name=st,
            reason="global_proxy_cap",
            selected_limit=g,
            mode="proxy",
        )
    if state.active_proxy_requests >= cap:
        return ConcurrencyDecision(
            allowed=False,
            store_name=st,
            reason="store_proxy_cap",
            selected_limit=cap,
            mode="proxy",
        )
    return ConcurrencyDecision(
        allowed=True,
        store_name=st,
        reason="proxy_admitted",
        selected_limit=cap,
        mode="proxy",
    )


def decide_batch_admission(
    store_name: str,
    state: RuntimeResourceState,
    budget: StoreResourceBudget,
) -> ConcurrencyDecision:
    st = (store_name or "").strip() or "unknown"
    if not getattr(settings, "ENABLE_RESOURCE_GOVERNANCE", True):
        return ConcurrencyDecision(
            allowed=True,
            store_name=st,
            reason="governance_disabled",
            selected_limit=budget.max_batch_inflight,
            mode="http",
        )
    g = int(getattr(settings, "GLOBAL_MAX_INFLIGHT_BATCHES", 4))
    cap = _cap(budget.max_batch_inflight, g)
    if get_global_inflight_batches_total() >= g:
        return ConcurrencyDecision(
            allowed=False,
            store_name=st,
            reason="global_batch_inflight_cap",
            selected_limit=g,
            mode="http",
        )
    if state.inflight_batches >= cap:
        return ConcurrencyDecision(
            allowed=False,
            store_name=st,
            reason="store_batch_inflight_cap",
            selected_limit=cap,
            mode="http",
        )
    return ConcurrencyDecision(
        allowed=True,
        store_name=st,
        reason="batch_admitted",
        selected_limit=cap,
        mode="http",
    )


def meta_to_resource_mode(meta: dict[str, Any]) -> ResourceMode:
    m = str(meta.get("access_mode_selected") or "plain").lower()
    if m == "browser":
        return "browser"
    if m == "proxy":
        return "proxy"
    return "http"
