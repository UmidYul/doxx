from __future__ import annotations

from domain.cost_efficiency import EfficiencySignal, StoreCostSnapshot
from application.performance.cost_degradation_advisor import (
    explain_cost_reduction_action,
    suggest_cost_reduction_action,
)


def test_browser_overuse_suggests_reduce_browser() -> None:
    snap = StoreCostSnapshot(store_name="s", status="acceptable")
    sigs = [
        EfficiencySignal(
            store_name="s",
            severity="high",
            signal_code="browser_overuse",
            observed_value=0.5,
            threshold_value=0.3,
            reason="policy",
        )
    ]
    assert suggest_cost_reduction_action(snap, sigs) == "reduce_browser"
    lines = explain_cost_reduction_action(snap, sigs)
    assert any("browser" in x.lower() for x in lines)


def test_retry_overuse() -> None:
    snap = StoreCostSnapshot(store_name="s", status="acceptable")
    sigs = [
        EfficiencySignal(
            store_name="s",
            severity="critical",
            signal_code="retry_overuse",
            observed_value=0.5,
            threshold_value=0.2,
            reason="r",
        )
    ]
    assert suggest_cost_reduction_action(snap, sigs) == "reduce_retry_budget"
