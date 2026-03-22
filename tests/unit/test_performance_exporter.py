from __future__ import annotations

from domain.performance import BottleneckSignal, RunPerformanceSnapshot, StorePerformanceSnapshot, utcnow
from infrastructure.performance.performance_exporter import (
    build_bottleneck_summary,
    build_run_performance_payload,
    build_store_performance_payload,
)


def test_exporter_compact_payload() -> None:
    ss = StorePerformanceSnapshot(
        store_name="x",
        requests_total=1,
        products_total=2,
        batches_total=1,
        avg_normalize_ms=12.5,
    )
    d = build_store_performance_payload(ss)
    assert d["kind"] == "store_performance_v1"
    assert d["store_name"] == "x"
    assert "avg_normalize_ms" in d

    run = RunPerformanceSnapshot(
        run_id="rid",
        started_at=utcnow(),
        stores=["x"],
        store_snapshots=[ss],
        slowest_stages=["normalize"],
    )
    r = build_run_performance_payload(run)
    assert r["kind"] == "run_performance_v1"
    assert r["run_id"] == "rid"
    assert isinstance(r["store_summaries"], list)

    sigs = [
        BottleneckSignal(
            stage="normalize",
            store_name="x",
            severity="warning",
            observed_ms=100.0,
            threshold_ms=50.0,
            reason="avg_normalization_cost_high",
        )
    ]
    b = build_bottleneck_summary(sigs)
    assert b["kind"] == "bottleneck_summary_v1"
    assert b["total_signals"] == 1
