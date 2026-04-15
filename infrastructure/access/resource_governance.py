from __future__ import annotations

import logging
from typing import Any

from config.settings import settings
from config.store_resource_budgets import get_store_budget
from domain.resource_governance import ResourceMode
from application.performance.concurrency_policy import (
    decide_browser_admission,
    decide_proxy_admission,
    decide_request_admission,
    meta_to_resource_mode,
)
from infrastructure.observability import message_codes as rg_mc
from infrastructure.observability.event_logger import log_resource_governance_event
from infrastructure.performance.resource_tracker import build_runtime_state

logger = logging.getLogger(__name__)


def _is_store_bypassed(store_name: str) -> bool:
    st = (store_name or "").strip().lower()
    if not st:
        return False
    raw = getattr(settings, "SCRAPY_RESOURCE_GOV_BYPASS_STORES", []) or []
    return st in {str(v).strip().lower() for v in raw if str(v).strip()}


def strip_browser_from_meta(meta: dict[str, Any]) -> None:
    meta.pop("playwright", None)
    meta.pop("playwright_page_goto_kwargs", None)
    meta.pop("playwright_page_init_callback", None)
    meta["access_mode_selected"] = "plain"


def strip_proxy_from_meta(meta: dict[str, Any]) -> None:
    meta.pop("proxy", None)
    if str(meta.get("access_mode_selected") or "") == "proxy":
        meta["access_mode_selected"] = "plain"


def _purpose_to_literal(purpose: str) -> str:
    p = (purpose or "").lower()
    if p == "product":
        return "product"
    return "listing"


def apply_governance_to_request_meta(
    store_name: str,
    purpose: str,
    meta: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Downgrade browser/proxy when over budget; then check admission. Mutates ``meta`` in place."""
    if not getattr(settings, "ENABLE_RESOURCE_GOVERNANCE", True):
        return meta, True
    if not getattr(settings, "ENABLE_STORE_RESOURCE_BUDGETS", True):
        return meta, True

    budget = get_store_budget(store_name)
    st = (store_name or "").strip() or "unknown"
    plit = _purpose_to_literal(purpose)
    if _is_store_bypassed(st):
        meta["_resource_gov_bypass"] = True
        log_resource_governance_event(
            rg_mc.RESOURCE_ADMISSION_ALLOWED,
            store_name=st,
            purpose=plit,
            mode=meta_to_resource_mode(meta),
            selected_limit=0,
            reason="store_bypass_configured",
        )
        return meta, True

    # Downgrade expensive modes if budgets are saturated (prefer plain HTTP).
    for _ in range(3):
        mode = meta_to_resource_mode(meta)
        state = build_runtime_state(st)
        if mode == "browser" and getattr(settings, "ENABLE_BROWSER_BUDGETS", True):
            bd = decide_browser_admission(st, state, budget)
            if not bd.allowed:
                log_resource_governance_event(
                    rg_mc.BROWSER_BUDGET_EXCEEDED,
                    store_name=st,
                    purpose=plit,
                    mode="browser",
                    inflight_requests=state.inflight_requests,
                    inflight_batches=state.inflight_batches,
                    retryable_queue=state.queued_retryable_items,
                    browser_pages=state.active_browser_pages,
                    proxy_requests=state.active_proxy_requests,
                    memory_mb=state.memory_mb,
                    selected_limit=bd.selected_limit,
                    reason=bd.reason,
                )
                strip_browser_from_meta(meta)
                continue
        if mode == "proxy" and getattr(settings, "ENABLE_PROXY_BUDGETS", True):
            pd = decide_proxy_admission(st, state, budget)
            if not pd.allowed:
                log_resource_governance_event(
                    rg_mc.PROXY_BUDGET_EXCEEDED,
                    store_name=st,
                    purpose=plit,
                    mode="proxy",
                    inflight_requests=state.inflight_requests,
                    inflight_batches=state.inflight_batches,
                    retryable_queue=state.queued_retryable_items,
                    browser_pages=state.active_browser_pages,
                    proxy_requests=state.active_proxy_requests,
                    memory_mb=state.memory_mb,
                    selected_limit=pd.selected_limit,
                    reason=pd.reason,
                )
                strip_proxy_from_meta(meta)
                continue
        break

    mode = meta_to_resource_mode(meta)
    state = build_runtime_state(st)
    dec = decide_request_admission(
        st,
        plit if plit == "product" else "listing",
        mode,
        state,
        budget,
    )
    if not dec.allowed:
        log_resource_governance_event(
            rg_mc.RESOURCE_ADMISSION_BLOCKED,
            store_name=st,
            purpose=plit,
            mode=mode,
            inflight_requests=state.inflight_requests,
            inflight_batches=state.inflight_batches,
            retryable_queue=state.queued_retryable_items,
            browser_pages=state.active_browser_pages,
            proxy_requests=state.active_proxy_requests,
            memory_mb=state.memory_mb,
            selected_limit=dec.selected_limit,
            reason=dec.reason,
        )
        return meta, False

    log_resource_governance_event(
        rg_mc.RESOURCE_ADMISSION_ALLOWED,
        store_name=st,
        purpose=plit,
        mode=mode,
        inflight_requests=state.inflight_requests,
        inflight_batches=state.inflight_batches,
        retryable_queue=state.queued_retryable_items,
        browser_pages=state.active_browser_pages,
        proxy_requests=state.active_proxy_requests,
        memory_mb=state.memory_mb,
        selected_limit=dec.selected_limit,
        reason=dec.reason,
    )
    return meta, True


def record_request_scheduled_governance(
    store_name: str,
    purpose: str,
    meta: dict[str, Any],
) -> None:
    """Increment in-flight trackers after a request is actually scheduled."""
    if not getattr(settings, "ENABLE_RESOURCE_GOVERNANCE", True):
        return
    from infrastructure.performance.resource_tracker import (
        increment_browser_pages,
        increment_inflight_request,
        increment_proxy_requests,
    )

    st = (store_name or "").strip() or "unknown"
    plit = _purpose_to_literal(purpose)
    if bool(meta.get("_resource_gov_bypass")):
        meta["_resource_gov"] = {
            "purpose": "product" if plit == "product" else "listing",
            "mode": str(meta.get("access_mode_selected") or "plain").lower(),
            "bypass": True,
        }
        if getattr(settings, "ENABLE_COST_EFFICIENCY_TRACKING", True):
            from infrastructure.performance.perf_collector import record_scheduled_request_cost

            record_scheduled_request_cost(store_name, meta)
        return
    increment_inflight_request(st, "product" if plit == "product" else "listing")
    sel = str(meta.get("access_mode_selected") or "plain").lower()
    if sel == "browser":
        increment_browser_pages(st)
    elif sel == "proxy":
        increment_proxy_requests(st)
    meta["_resource_gov"] = {
        "purpose": "product" if plit == "product" else "listing",
        "mode": sel,
    }
    if getattr(settings, "ENABLE_COST_EFFICIENCY_TRACKING", True):
        from infrastructure.performance.perf_collector import record_scheduled_request_cost

        record_scheduled_request_cost(store_name, meta)


def release_request_governance_counters(response_meta: dict[str, Any], store_name: str) -> None:
    """Release counters when a response is handled (parse/errback)."""
    if not getattr(settings, "ENABLE_RESOURCE_GOVERNANCE", True):
        return
    from infrastructure.performance.resource_tracker import (
        decrement_browser_pages,
        decrement_inflight_request,
        decrement_proxy_requests,
    )

    st = (store_name or "").strip() or "unknown"
    gov = response_meta.get("_resource_gov") if isinstance(response_meta, dict) else None
    if not isinstance(gov, dict):
        return
    if bool(gov.get("bypass")):
        return
    purpose = str(gov.get("purpose") or "listing")
    mode = str(gov.get("mode") or "plain").lower()
    decrement_inflight_request(st, purpose)
    if mode == "browser":
        decrement_browser_pages(st)
    elif mode == "proxy":
        decrement_proxy_requests(st)
