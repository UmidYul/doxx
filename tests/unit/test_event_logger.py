from __future__ import annotations

import json

import pytest

from config import settings as settings_mod
from domain.observability import SyncCorrelationContext

from infrastructure.observability.event_logger import log_sync_event
from infrastructure.observability import message_codes as mc
from infrastructure.observability.metrics_collector import (
    get_observability_metrics,
    reset_observability_metrics_for_tests,
)
from infrastructure.observability.trace_collector import get_trace_collector, reset_trace_collector_for_tests


def test_log_sync_event_emits_structured_fields(caplog, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings_mod.settings, "ENABLE_STRUCTURED_SYNC_LOGS", True)
    monkeypatch.setattr(settings_mod.settings, "ENABLE_IN_MEMORY_TRACE_BUFFER", True)
    reset_trace_collector_for_tests()
    reset_observability_metrics_for_tests()
    get_trace_collector().set_run_context(run_id="run-z", stores=["st"])

    corr = SyncCorrelationContext(
        run_id="run-z",
        spider_name="sp",
        store_name="st",
        entity_key="ek",
    )
    with caplog.at_level("INFO", logger="moscraper.observability.sync"):
        log_sync_event(
            "normalize",
            "info",
            mc.NORMALIZATION_COMPLETED,
            corr,
            metrics={"n": 1},
            details={"k": "v"},
        )

    assert caplog.records, "expected log record"
    raw = caplog.records[-1].getMessage()
    assert raw.startswith("sync_event ")
    payload = json.loads(raw.split(" ", 1)[1])
    assert payload["observability"] == "parser_sync_v1"
    assert payload["stage"] == "normalize"
    assert payload["message_code"] == mc.NORMALIZATION_COMPLETED
    assert payload["correlation"]["run_id"] == "run-z"
    assert payload["correlation"]["entity_key"] == "ek"

    traces = get_trace_collector().get_recent_traces(5)
    assert traces[-1].message_code == mc.NORMALIZATION_COMPLETED
    assert get_observability_metrics().snapshot().get("normalization_items_total", 0) >= 1
