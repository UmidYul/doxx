from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from config.settings import Settings
from domain.observability import ParserHealthSnapshot
from infrastructure.observability.etl_status_exporter import build_etl_status_payload
from infrastructure.observability.support_serializer import serialize_diagnostic_snapshot


def test_etl_status_payload_still_has_schema() -> None:
    health = MagicMock(spec=ParserHealthSnapshot)
    health.run_id = "r1"
    health.started_at = MagicMock()
    health.started_at.isoformat = MagicMock(return_value="2026-01-01T00:00:00Z")
    health.stores = []
    health.counters = {}
    health.last_errors = []
    health.status = "healthy"
    health.error_aggregates_by_domain = {}
    health.dashboard_summary = {}
    health.operational_alerts = []
    health.threshold_decisions = []
    health.serialized_run_operational = {}
    health.operator_support = {}

    payload = build_etl_status_payload(health, [], [])
    assert payload.get("schema") == "parser_etl_status_v3"


def test_diagnostic_snapshot_serializer_minimized(monkeypatch: pytest.MonkeyPatch) -> None:
    s = Settings(
        _env_file=None,
        ENABLE_DATA_MINIMIZATION=True,
        ENABLE_SAFE_DIAGNOSTIC_EXPORTS=True,
        DIAGNOSTIC_SNAPSHOT_MAX_ITEMS=3,
    )  # type: ignore[arg-type]
    monkeypatch.setattr(
        "infrastructure.observability.support_serializer.settings",
        s,
    )
    snap = {
        "kind": "run",
        "run_id": "x",
        "top_alerts": [{"a": i} for i in range(10)],
        "recent_failed_items_sample": [],
    }
    out = serialize_diagnostic_snapshot(snap)
    assert isinstance(out.get("top_alerts"), list)
    assert len(out["top_alerts"]) <= 3
