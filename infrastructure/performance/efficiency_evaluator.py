from __future__ import annotations

from typing import Any

from domain.cost_efficiency import CostEfficiencyStatus, EfficiencySignal, RunCostSnapshot, StoreCostSnapshot


def _f(settings: Any, name: str, default: float) -> float:
    return float(getattr(settings, name, default))


def evaluate_store_efficiency(snapshot: StoreCostSnapshot, settings: Any) -> list[EfficiencySignal]:
    if not getattr(settings, "ENABLE_COST_EFFICIENCY_TRACKING", True):
        return []

    signals: list[EfficiencySignal] = []
    st = snapshot.store_name
    cost = max(snapshot.estimated_cost_units, 1e-9)

    min_ppc = _f(settings, "EFFICIENCY_MIN_PRODUCTS_PER_COST_UNIT", 0.5)
    min_apc = _f(settings, "EFFICIENCY_MIN_APPLIED_PER_COST_UNIT", 0.4)
    max_browser_share = _f(settings, "EFFICIENCY_MAX_BROWSER_SHARE", 0.30)
    max_retry_share = _f(settings, "EFFICIENCY_MAX_RETRY_SHARE", 0.20)
    max_proxy_share = _f(settings, "EFFICIENCY_MAX_PROXY_SHARE", 0.40)

    w_b = _f(settings, "COST_WEIGHT_BROWSER_PAGE", 5.0)
    w_r = _f(settings, "COST_WEIGHT_RETRY_ATTEMPT", 1.5)
    w_p = _f(settings, "COST_WEIGHT_PROXY_REQUEST", 2.0)
    w_crm = _f(settings, "COST_WEIGHT_CRM_ROUNDTRIP", 1.0)

    browser_share = (w_b * float(snapshot.browser_pages)) / cost
    retry_share = (w_r * float(snapshot.retry_attempts)) / cost
    proxy_share = (w_p * float(snapshot.proxy_requests)) / cost
    crm_share = (w_crm * float(snapshot.crm_roundtrips)) / cost

    if snapshot.products_per_cost_unit is not None and snapshot.products_per_cost_unit < min_ppc:
        signals.append(
            EfficiencySignal(
                store_name=st,
                severity="high",
                signal_code="low_products_per_cost_unit",
                observed_value=float(snapshot.products_per_cost_unit),
                threshold_value=min_ppc,
                reason="throughput_per_cost_below_minimum",
            )
        )

    if snapshot.applied_per_cost_unit is not None and snapshot.applied_per_cost_unit < min_apc:
        signals.append(
            EfficiencySignal(
                store_name=st,
                severity="warning",
                signal_code="low_applied_per_cost_unit",
                observed_value=float(snapshot.applied_per_cost_unit),
                threshold_value=min_apc,
                reason="crm_apply_yield_per_cost_below_minimum",
            )
        )

    if browser_share > max_browser_share:
        signals.append(
            EfficiencySignal(
                store_name=st,
                severity="high" if browser_share > max_browser_share * 1.3 else "warning",
                signal_code="browser_overuse",
                observed_value=browser_share,
                threshold_value=max_browser_share,
                reason="browser_cost_share_exceeds_policy",
            )
        )

    if retry_share > max_retry_share:
        signals.append(
            EfficiencySignal(
                store_name=st,
                severity="critical" if retry_share > max_retry_share * 1.5 else "high",
                signal_code="retry_overuse",
                observed_value=retry_share,
                threshold_value=max_retry_share,
                reason="retry_cost_share_exceeds_policy",
            )
        )

    if proxy_share > max_proxy_share:
        signals.append(
            EfficiencySignal(
                store_name=st,
                severity="warning" if proxy_share < max_proxy_share * 1.2 else "high",
                signal_code="proxy_overuse",
                observed_value=proxy_share,
                threshold_value=max_proxy_share,
                reason="proxy_cost_share_exceeds_policy",
            )
        )

    if crm_share > 0.35 and snapshot.products_applied > 0:
        signals.append(
            EfficiencySignal(
                store_name=st,
                severity="warning",
                signal_code="crm_roundtrip_heavy",
                observed_value=crm_share,
                threshold_value=0.35,
                reason="crm_batch_cost_share_high",
            )
        )

    req_total = snapshot.http_requests + snapshot.proxy_requests + snapshot.browser_pages
    if req_total > 0 and snapshot.products_parsed > 0:
        yield_ratio = snapshot.products_parsed / float(req_total)
        if yield_ratio < 0.05 and snapshot.estimated_cost_units > 10:
            signals.append(
                EfficiencySignal(
                    store_name=st,
                    severity="high",
                    signal_code="expensive_low_yield_store",
                    observed_value=yield_ratio,
                    threshold_value=0.05,
                    reason="many_requests_per_product_parsed",
                )
            )

    return signals


def evaluate_run_efficiency(snapshot: RunCostSnapshot, settings: Any) -> list[EfficiencySignal]:
    if not getattr(settings, "ENABLE_COST_EFFICIENCY_TRACKING", True):
        return []

    out: list[EfficiencySignal] = []
    total_cost = max(snapshot.total_estimated_cost_units, 1e-9)
    if total_cost > 1000 and snapshot.store_snapshots:
        worst = min(
            snapshot.store_snapshots,
            key=lambda s: s.products_per_cost_unit if s.products_per_cost_unit is not None else -1.0,
        )
        if worst.products_per_cost_unit is not None and worst.products_per_cost_unit < _f(
            settings,
            "EFFICIENCY_MIN_PRODUCTS_PER_COST_UNIT",
            0.5,
        ):
            out.append(
                EfficiencySignal(
                    store_name=None,
                    severity="warning",
                    signal_code="run_low_efficiency_tail",
                    observed_value=float(worst.products_per_cost_unit),
                    threshold_value=_f(settings, "EFFICIENCY_MIN_PRODUCTS_PER_COST_UNIT", 0.5),
                    reason="at_least_one_store_below_efficiency_floor",
                )
            )

    return out


def classify_store_cost_status(snapshot: StoreCostSnapshot, signals: list[EfficiencySignal]) -> CostEfficiencyStatus:
    if any(s.severity == "critical" for s in signals):
        return "critical"
    if any(s.severity == "high" for s in signals):
        return "expensive"
    if any(s.severity == "warning" for s in signals):
        return "acceptable"
    if snapshot.estimated_cost_units <= 0:
        return "acceptable"
    ppc = snapshot.products_per_cost_unit
    if ppc is not None and ppc >= 1.0:
        return "efficient"
    return "acceptable"
