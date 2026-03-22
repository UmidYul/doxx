from __future__ import annotations

from types import SimpleNamespace

from domain.cost_efficiency import RunCostSnapshot, StoreCostSnapshot
from infrastructure.performance.efficiency_evaluator import (
    classify_store_cost_status,
    evaluate_store_efficiency,
)


def _settings(**kwargs: float | bool) -> SimpleNamespace:
    base = dict(
        ENABLE_COST_EFFICIENCY_TRACKING=True,
        EFFICIENCY_MIN_PRODUCTS_PER_COST_UNIT=0.5,
        EFFICIENCY_MIN_APPLIED_PER_COST_UNIT=0.4,
        EFFICIENCY_MAX_BROWSER_SHARE=0.30,
        EFFICIENCY_MAX_RETRY_SHARE=0.20,
        EFFICIENCY_MAX_PROXY_SHARE=0.40,
        COST_WEIGHT_BROWSER_PAGE=5.0,
        COST_WEIGHT_RETRY_ATTEMPT=1.5,
        COST_WEIGHT_PROXY_REQUEST=2.0,
        COST_WEIGHT_CRM_ROUNDTRIP=1.0,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_low_products_per_cost_emits_signal() -> None:
    snap = StoreCostSnapshot(
        store_name="s",
        http_requests=100,
        products_parsed=5,
        estimated_cost_units=50.0,
        products_per_cost_unit=0.1,
        applied_per_cost_unit=0.1,
    )
    sigs = evaluate_store_efficiency(snap, _settings())
    assert any(s.signal_code == "low_products_per_cost_unit" for s in sigs)


def test_expensive_low_yield() -> None:
    snap = StoreCostSnapshot(
        store_name="s",
        http_requests=500,
        proxy_requests=0,
        browser_pages=0,
        products_parsed=10,
        estimated_cost_units=200.0,
        products_per_cost_unit=0.05,
    )
    sigs = evaluate_store_efficiency(snap, _settings())
    assert any(s.signal_code == "expensive_low_yield_store" for s in sigs)


def test_classify_critical_from_signals() -> None:
    snap = StoreCostSnapshot(store_name="s", estimated_cost_units=10.0)
    from domain.cost_efficiency import EfficiencySignal

    sigs = [
        EfficiencySignal(
            store_name="s",
            severity="critical",
            signal_code="retry_overuse",
            observed_value=1.0,
            threshold_value=0.2,
            reason="x",
        )
    ]
    assert classify_store_cost_status(snap, sigs) == "critical"
