from __future__ import annotations

from domain.cost_efficiency import EfficiencySignal, RunCostSnapshot, StoreCostSnapshot
from infrastructure.performance.cost_exporter import (
    build_efficiency_signal_payload,
    build_run_cost_payload,
    build_store_cost_payload,
)


def test_build_store_cost_payload_compact() -> None:
    s = StoreCostSnapshot(
        store_name="x",
        estimated_cost_units=12.5,
        products_per_cost_unit=2.0,
        applied_per_cost_unit=1.5,
        status="acceptable",
    )
    p = build_store_cost_payload(s)
    assert p["kind"] == "store_cost_v1"
    assert "mix" in p
    assert len(p) <= 12


def test_build_run_cost_payload() -> None:
    r = RunCostSnapshot(
        run_id="r1",
        store_snapshots=[StoreCostSnapshot(store_name="a", estimated_cost_units=3.0)],
        total_estimated_cost_units=3.0,
        highest_cost_stores=["a"],
        lowest_efficiency_stores=["a"],
    )
    p = build_run_cost_payload(r)
    assert p["kind"] == "run_cost_v1"
    assert p["run_id"] == "r1"


def test_build_efficiency_signal_payload() -> None:
    sigs = [
        EfficiencySignal(
            store_name="s",
            severity="warning",
            signal_code="proxy_overuse",
            observed_value=0.5,
            threshold_value=0.4,
            reason="r",
        )
    ]
    p = build_efficiency_signal_payload(sigs)
    assert p["count"] == 1
    assert p["items"][0]["signal_code"] == "proxy_overuse"
