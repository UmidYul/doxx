from __future__ import annotations

from typing import Literal

from domain.cost_efficiency import EfficiencySignal, StoreCostSnapshot

CostReductionAction = Literal[
    "none",
    "reduce_browser",
    "reduce_proxy",
    "reduce_retry_budget",
    "reduce_diagnostics",
    "reduce_crawl_scope",
    "pause_expensive_store",
]


def suggest_cost_reduction_action(
    store_snapshot: StoreCostSnapshot,
    signals: list[EfficiencySignal],
) -> CostReductionAction:
    codes = {s.signal_code for s in signals}
    if "retry_overuse" in codes or "expensive_low_yield_store" in codes:
        if "expensive_low_yield_store" in codes:
            return "reduce_crawl_scope"
        return "reduce_retry_budget"
    if "browser_overuse" in codes:
        return "reduce_browser"
    if "proxy_overuse" in codes:
        return "reduce_proxy"
    if "crm_roundtrip_heavy" in codes:
        return "reduce_diagnostics"
    if store_snapshot.status == "critical":
        return "pause_expensive_store"
    if store_snapshot.status == "expensive":
        return "reduce_crawl_scope"
    return "none"


def explain_cost_reduction_action(
    store_snapshot: StoreCostSnapshot,
    signals: list[EfficiencySignal],
) -> list[str]:
    action = suggest_cost_reduction_action(store_snapshot, signals)
    lines = [
        f"store={store_snapshot.store_name!r}",
        f"recommended_action={action!r}",
        f"estimated_cost_units={store_snapshot.estimated_cost_units}",
    ]
    for s in signals:
        lines.append(f"signal={s.signal_code!r} severity={s.severity!r} reason={s.reason!r}")
    if action == "reduce_browser":
        lines.append("hint: tighten browser escalation / caps (advisory)")
    elif action == "reduce_proxy":
        lines.append("hint: prefer plain HTTP where policy allows (advisory)")
    elif action == "reduce_retry_budget":
        lines.append("hint: backoff retries to avoid cost sink (advisory)")
    elif action == "reduce_diagnostics":
        lines.append("hint: trim observability/diagnostic stages on hot paths (advisory)")
    elif action == "reduce_crawl_scope":
        lines.append("hint: narrow categories or rate-limit crawl (advisory)")
    elif action == "pause_expensive_store":
        lines.append("hint: operator review before continuing this store (advisory)")
    return lines
