from __future__ import annotations

import pytest

from config import settings as settings_mod
from domain.performance import RunPerformanceSnapshot, StorePerformanceSnapshot, utcnow
from infrastructure.performance.bottleneck_detector import (
    classify_store_performance,
    detect_bottlenecks,
    is_stage_slow,
)


def test_slow_normalize_detected() -> None:
    assert is_stage_slow("normalize", 800.0, settings_mod.settings) is True
    assert is_stage_slow("normalize", 100.0, settings_mod.settings) is False


def test_slow_crm_send_detected() -> None:
    assert is_stage_slow("crm_send", 5000.0, settings_mod.settings) is True


def test_low_throughput_signal() -> None:
    snap = RunPerformanceSnapshot(
        run_id="r",
        started_at=utcnow(),
        stores=["s"],
        store_snapshots=[
            StorePerformanceSnapshot(
                store_name="s",
                requests_total=100,
                products_total=50,
                batches_total=2,
                products_per_minute=0.5,
            )
        ],
    )
    sigs = detect_bottlenecks(snap, settings_mod.settings)
    reasons = [s.reason for s in sigs]
    assert any("low_products_per_minute" in r for r in reasons)


def test_memory_critical_bottleneck() -> None:
    st = StorePerformanceSnapshot(
        store_name="s",
        memory_estimate_mb=float(settings_mod.settings.PERF_CRITICAL_MEMORY_MB + 100),
        products_total=5,
    )
    assert classify_store_performance(st, settings_mod.settings) == "critical"
    snap = RunPerformanceSnapshot(
        run_id="r",
        started_at=utcnow(),
        stores=["s"],
        store_snapshots=[st],
    )
    sigs = detect_bottlenecks(snap, settings_mod.settings)
    assert any(s.severity == "critical" for s in sigs)
