from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

from domain.cost_efficiency import RunCostSnapshot, StoreCostSnapshot
from domain.performance import RunPerformanceSnapshot, StorePerformanceSnapshot
from application.performance.efficiency_baseline import (
    build_efficiency_baseline_from_snapshot,
    load_efficiency_baseline,
    save_efficiency_baseline,
)


def test_save_load_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = str(Path(d) / "baseline.json")
        b = {"avg_request_ms": 120.5, "cost_per_product": 2.0}
        save_efficiency_baseline(p, b)
        assert load_efficiency_baseline(p) == b


def test_build_efficiency_baseline_from_snapshots() -> None:
    run = RunPerformanceSnapshot(
        run_id="r",
        started_at=datetime.now(UTC),
        stores=["s"],
        store_snapshots=[
            StorePerformanceSnapshot(
                store_name="s",
                avg_request_ms=100.0,
                avg_normalize_ms=50.0,
                avg_crm_send_ms=200.0,
                products_per_minute=30.0,
            )
        ],
    )
    cost = RunCostSnapshot(
        run_id="r",
        store_snapshots=[
            StoreCostSnapshot(
                store_name="s",
                products_parsed=100,
                products_applied=80,
                estimated_cost_units=50.0,
            )
        ],
        total_estimated_cost_units=50.0,
    )
    flat = build_efficiency_baseline_from_snapshot(run, cost)
    assert "avg_request_ms" in flat
    assert flat["cost_per_product"] == 0.5
    assert flat["cost_per_applied_item"] == 50.0 / 80.0
