from __future__ import annotations

from typing import Any

from domain.cost_efficiency import CostEfficiencyStatus, RunCostSnapshot, StoreCostSnapshot
from infrastructure.performance.efficiency_evaluator import (
    classify_store_cost_status,
    evaluate_run_efficiency,
    evaluate_store_efficiency,
)


def compute_products_per_cost_unit(products: int, cost_units: float) -> float | None:
    if products <= 0 or cost_units <= 0:
        return None
    return float(products) / float(cost_units)


def estimate_store_cost_units(counters: dict[str, int | float], settings: Any) -> float:
    s = settings
    if not getattr(s, "ENABLE_COST_EFFICIENCY_TRACKING", True):
        return 0.0

    def _i(key: str) -> int:
        v = counters.get(key, 0)
        return int(v) if isinstance(v, (int, float)) else 0

    def _f(key: str) -> float:
        v = counters.get(key, 0.0)
        return float(v) if isinstance(v, (int, float)) else 0.0

    http = _i("http_requests")
    proxy = _i("proxy_requests")
    browser = _i("browser_pages")
    retry = _i("retry_attempts")
    batches = _i("batch_flushes")
    crm = _i("crm_roundtrips")
    norm = _f("normalization_units")
    diag = _f("diagnostic_units")

    w_http = float(getattr(s, "COST_WEIGHT_HTTP_REQUEST", 1.0))
    w_proxy = float(getattr(s, "COST_WEIGHT_PROXY_REQUEST", 2.0))
    w_browser = float(getattr(s, "COST_WEIGHT_BROWSER_PAGE", 5.0))
    w_retry = float(getattr(s, "COST_WEIGHT_RETRY_ATTEMPT", 1.5))
    w_batch = float(getattr(s, "COST_WEIGHT_BATCH_FLUSH", 0.5))
    w_crm = float(getattr(s, "COST_WEIGHT_CRM_ROUNDTRIP", 1.0))
    w_norm = float(getattr(s, "COST_WEIGHT_NORMALIZATION_UNIT", 0.5))
    w_diag = float(getattr(s, "COST_WEIGHT_DIAGNOSTIC_UNIT", 0.2))

    return (
        w_http * http
        + w_proxy * proxy
        + w_browser * browser
        + w_retry * retry
        + w_batch * batches
        + w_crm * crm
        + w_norm * norm
        + w_diag * diag
    )


def build_store_cost_snapshot(
    store_name: str,
    counters: dict[str, int | float],
    settings: Any,
) -> StoreCostSnapshot:
    st = (store_name or "").strip() or "unknown"
    cost = estimate_store_cost_units(counters, settings)

    def _i(key: str) -> int:
        v = counters.get(key, 0)
        return int(v) if isinstance(v, (int, float)) else 0

    products_parsed = _i("products_parsed")
    products_applied = _i("products_applied")

    ppc = compute_products_per_cost_unit(products_parsed, cost)
    apc = compute_products_per_cost_unit(products_applied, cost)

    snap = StoreCostSnapshot(
        store_name=st,
        http_requests=_i("http_requests"),
        proxy_requests=_i("proxy_requests"),
        browser_pages=_i("browser_pages"),
        retry_attempts=_i("retry_attempts"),
        batch_flushes=_i("batch_flushes"),
        crm_roundtrips=_i("crm_roundtrips"),
        products_parsed=products_parsed,
        products_applied=products_applied,
        estimated_cost_units=cost,
        products_per_cost_unit=ppc,
        applied_per_cost_unit=apc,
        status="acceptable",
    )
    signals = evaluate_store_efficiency(snap, settings)
    status = classify_store_cost_status(snap, signals)
    return snap.model_copy(update={"status": status})


def _rank_status(a: CostEfficiencyStatus, b: CostEfficiencyStatus) -> CostEfficiencyStatus:
    order = {"efficient": 0, "acceptable": 1, "expensive": 2, "critical": 3}
    return a if order[a] >= order[b] else b


def build_run_cost_snapshot(
    run_id: str,
    store_counters: dict[str, dict[str, int | float]],
    settings: Any,
) -> RunCostSnapshot:
    rid = (run_id or "").strip() or "unknown"
    snaps: list[StoreCostSnapshot] = []
    total = 0.0
    for store_name, ctr in sorted(store_counters.items()):
        s = build_store_cost_snapshot(store_name, ctr, settings)
        snaps.append(s)
        total += s.estimated_cost_units

    by_cost = sorted(snaps, key=lambda x: x.estimated_cost_units, reverse=True)
    highest = [x.store_name for x in by_cost[:5] if x.estimated_cost_units > 0]

    def _eff_key(x: StoreCostSnapshot) -> float:
        v = x.products_per_cost_unit
        return v if v is not None else -1.0

    by_eff = sorted(snaps, key=_eff_key)
    lowest = [x.store_name for x in by_eff[:5]]

    run_snap = RunCostSnapshot(
        run_id=rid,
        store_snapshots=snaps,
        total_estimated_cost_units=total,
        highest_cost_stores=highest,
        lowest_efficiency_stores=lowest,
        overall_status="acceptable",
    )
    run_signals = evaluate_run_efficiency(run_snap, settings)
    if not snaps:
        overall: CostEfficiencyStatus = "acceptable"
    else:
        overall = "efficient"
        for s in snaps:
            overall = _rank_status(overall, s.status)
    for sig in run_signals:
        if sig.severity == "critical":
            overall = _rank_status(overall, "critical")
        elif sig.severity == "high":
            overall = _rank_status(overall, "expensive")
        else:
            overall = _rank_status(overall, "acceptable")
    return run_snap.model_copy(update={"overall_status": overall})
