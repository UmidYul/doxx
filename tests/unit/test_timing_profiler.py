from __future__ import annotations

import pytest

from config import settings as settings_mod
from domain.performance import StageTimingRecord, utcnow
from infrastructure.performance.timing_profiler import (
    get_recent_timings,
    record_timing,
    reset_timing_profiler_for_tests,
    start_stage,
    timed_stage,
    finish_stage,
)


def test_stage_timing_duration_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings_mod.settings, "ENABLE_PERFORMANCE_PROFILING", True)
    monkeypatch.setattr(settings_mod.settings, "ENABLE_STAGE_TIMING", True)
    monkeypatch.setattr(settings_mod.settings, "STAGE_TIMING_BUFFER_MAX_RECORDS", 100)
    reset_timing_profiler_for_tests()
    tok = start_stage("normalize", store_name="s1", spider_name="sp")
    rec = finish_stage(tok)
    assert rec.stage == "normalize"
    assert rec.duration_ms >= 0.0
    assert rec.store_name == "s1"
    recent = get_recent_timings(10)
    assert recent
    assert recent[-1].duration_ms == rec.duration_ms


def test_stage_buffer_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings_mod.settings, "ENABLE_PERFORMANCE_PROFILING", True)
    monkeypatch.setattr(settings_mod.settings, "ENABLE_STAGE_TIMING", True)
    monkeypatch.setattr(settings_mod.settings, "STAGE_TIMING_BUFFER_MAX_RECORDS", 5)
    reset_timing_profiler_for_tests()
    for i in range(20):
        record_timing(
            StageTimingRecord(
                stage="observability",
                started_at=utcnow(),
                finished_at=utcnow(),
                duration_ms=float(i),
                notes=[str(i)],
            )
        )
    all_recs = get_recent_timings(500)
    assert len(all_recs) <= 5


def test_timed_stage_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings_mod.settings, "ENABLE_PERFORMANCE_PROFILING", True)
    monkeypatch.setattr(settings_mod.settings, "ENABLE_STAGE_TIMING", True)
    reset_timing_profiler_for_tests()
    with timed_stage("listing_parse", store_name="st"):
        pass
    assert get_recent_timings(1)[-1].stage == "listing_parse"
