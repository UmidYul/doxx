from __future__ import annotations

from typing import Literal

from domain.resource_governance import BackpressureDecision, RuntimeResourceState


def suggest_degradation_mode(
    store_name: str,
    state: RuntimeResourceState,
    decision: BackpressureDecision,
) -> Literal[
    "none",
    "reduce_browser",
    "disable_browser",
    "reduce_proxy",
    "reduce_crawl",
    "pause_store",
]:
    """Advisory degradation label for operators (no hard enforcement by default)."""
    _ = store_name
    if not decision.apply_backpressure:
        return "none"
    if decision.severity == "critical":
        if decision.reason.startswith("memory"):
            return "pause_store"
        if "retryable" in decision.reason or "batch_inflight" in decision.reason:
            return "reduce_crawl"
    if decision.suggested_action == "reduce_browser":
        return "reduce_browser" if state.active_browser_pages > 0 else "none"
    if decision.suggested_action == "reduce_proxy":
        return "reduce_proxy" if state.active_proxy_requests > 0 else "none"
    if state.active_browser_pages > 0 and decision.severity in ("high", "critical"):
        return "disable_browser"
    if decision.suggested_action == "slow_down":
        return "reduce_crawl"
    return "none"


def explain_degradation_mode(
    store_name: str,
    state: RuntimeResourceState,
    decision: BackpressureDecision,
) -> list[str]:
    mode = suggest_degradation_mode(store_name, state, decision)
    lines = [
        f"store={store_name!r}",
        f"suggested_mode={mode!r}",
        f"backpressure_reason={decision.reason!r}",
        f"severity={decision.severity!r}",
    ]
    if mode == "disable_browser":
        lines.append("hint: prefer plain HTTP until pressure drops (advisory)")
    if mode == "reduce_crawl":
        lines.append("hint: fewer concurrent listing/product requests (advisory)")
    if mode == "pause_store":
        lines.append("hint: investigate memory or stop crawl if operator policy allows (advisory)")
    return lines
