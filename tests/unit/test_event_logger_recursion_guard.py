from __future__ import annotations

from domain.observability import SyncCorrelationContext
from infrastructure.observability import event_logger


def test_log_sync_event_trim_guard_blocks_recursive_trim(monkeypatch) -> None:
    monkeypatch.setattr(event_logger.settings, "ENABLE_STRUCTURED_SYNC_LOGS", True)
    monkeypatch.setattr(event_logger.settings, "ENABLE_IN_MEMORY_TRACE_BUFFER", False)
    monkeypatch.setattr(event_logger.settings, "ENABLE_SECRET_REDACTION", False)
    monkeypatch.setattr(event_logger.settings, "ENABLE_DATA_MINIMIZATION", False)
    monkeypatch.setattr(event_logger.settings, "ENABLE_PERFORMANCE_PROFILING", False)
    monkeypatch.setattr(event_logger.settings, "ENABLE_STAGE_TIMING", False)

    corr = SyncCorrelationContext(run_id="r1", spider_name="s1", store_name="alifshop")
    calls = {"trim": 0}

    def _fake_trim() -> None:
        calls["trim"] += 1
        if calls["trim"] == 1:
            event_logger.log_sync_event("internal", "info", "DEV_MODE_ENABLED", corr)

    monkeypatch.setattr(event_logger, "trim_buffers_if_needed", _fake_trim)
    event_logger.log_sync_event("internal", "info", "DEV_MODE_ENABLED", corr)
    assert calls["trim"] == 1
