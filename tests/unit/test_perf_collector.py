from __future__ import annotations

import pytest

from config import settings as settings_mod
from infrastructure.performance.perf_collector import (
    build_run_snapshot,
    build_store_snapshot,
    increment_counter,
    record_duration,
    reset_perf_collector_for_tests,
    set_run_context,
)


def test_store_snapshot_aggregates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings_mod.settings, "ENABLE_PERFORMANCE_PROFILING", True)
    reset_perf_collector_for_tests()
    set_run_context(run_id="r1", stores=["alpha"])
    increment_counter("requests", 10, store_name="alpha")
    increment_counter("products", 3, store_name="alpha")
    increment_counter("batches", 1, store_name="alpha")
    record_duration("normalize", 100.0, store_name="alpha")
    record_duration("normalize", 200.0, store_name="alpha")
    snap = build_store_snapshot("alpha")
    assert snap.requests_total == 10
    assert snap.products_total == 3
    assert snap.batches_total == 1
    assert snap.avg_normalize_ms == 150.0


def test_run_snapshot_stage_averages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings_mod.settings, "ENABLE_PERFORMANCE_PROFILING", True)
    monkeypatch.setattr(settings_mod.settings, "ENABLE_STORE_PERFORMANCE_SNAPSHOT", False)
    reset_perf_collector_for_tests()
    record_duration("crm_send", 400.0, store_name="b")
    record_duration("crm_send", 600.0, store_name="b")
    run = build_run_snapshot("run-x", ["b"])
    assert run.stage_averages_ms.get("crm_send") == 500.0
    assert "crm_send" in run.slowest_stages or run.slowest_stages
