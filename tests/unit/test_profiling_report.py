from __future__ import annotations

from domain.performance import BottleneckSignal, RunPerformanceSnapshot, StorePerformanceSnapshot, utcnow
from application.performance.profiling_report import build_human_profiling_report, build_profiling_report


def test_profiling_report_slowest_stores_and_stages() -> None:
    s1 = StorePerformanceSnapshot(
        store_name="heavy",
        avg_normalize_ms=900.0,
        avg_crm_send_ms=50.0,
        avg_request_ms=10.0,
        products_per_minute=3.0,
    )
    s2 = StorePerformanceSnapshot(
        store_name="light",
        avg_normalize_ms=10.0,
        avg_crm_send_ms=10.0,
        avg_request_ms=10.0,
        products_per_minute=30.0,
    )
    run = RunPerformanceSnapshot(
        run_id="r1",
        started_at=utcnow(),
        stores=["heavy", "light"],
        stage_averages_ms={"normalize": 400.0, "crm_send": 50.0},
        store_snapshots=[s1, s2],
        slowest_stages=["normalize", "crm_send"],
    )
    bots = [
        BottleneckSignal(
            stage="normalize",
            store_name="heavy",
            severity="high",
            observed_ms=900.0,
            threshold_ms=500.0,
            reason="avg_normalization_cost_high",
        )
    ]
    rep = build_profiling_report(run, bots)
    assert "heavy" in rep["slowest_stores"][0]
    assert "normalize" in rep["slowest_stages"]
    assert "normalization" in rep["recommendations"][0]

    text = build_human_profiling_report(run, bots)
    assert "Profiling report" in text
    assert "normalize" in text
