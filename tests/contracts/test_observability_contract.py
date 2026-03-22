from __future__ import annotations

import json
from pathlib import Path

from tests.helpers.builders import build_etl_status_fixture

TESTS_ROOT = Path(__file__).resolve().parents[1]
ETL_BASELINE = TESTS_ROOT / "fixtures" / "regression" / "observability" / "etl_export_baseline.json"

REQUIRED_ETL_EXPORT_KEYS = frozenset(
    {
        "schema",
        "run_id",
        "current_status",
        "operator_support",
        "triage_summary",
        "diagnostic_snapshot",
        "dashboard_summary",
    }
)

REQUIRED_DIAGNOSTIC_KEYS = frozenset(
    {
        "kind",
        "run_id",
        "current_status",
        "top_alerts",
        "recommended_action",
        "runbook_domain",
    }
)

def test_etl_export_baseline_file_matches_minimum_contract():
    raw = json.loads(ETL_BASELINE.read_text(encoding="utf-8"))
    missing = REQUIRED_ETL_EXPORT_KEYS - set(raw)
    assert not missing, missing


def test_build_etl_status_fixture_covers_v3_contract():
    f = build_etl_status_fixture(
        triage_summary={"run_id": "x", "domain": "internal"},
        diagnostic_snapshot={"kind": "run", "run_id": "x", "current_status": "healthy", "top_alerts": [], "recommended_action": "continue", "runbook_domain": "internal"},
        operator_support={
            "triage_run": {"run_id": "x"},
            "operator_headline": "h",
            "recommended_operator_action": "continue",
        },
    )
    assert REQUIRED_ETL_EXPORT_KEYS <= set(f)


def test_diagnostic_snapshot_contract_keys(monkeypatch):
    monkeypatch.setattr(
        "infrastructure.observability.diagnostic_snapshot.settings.ENABLE_DIAGNOSTIC_SNAPSHOTS",
        True,
    )
    from infrastructure.observability.diagnostic_snapshot import build_run_diagnostic_snapshot
    from domain.operational_policy import RunOperationalStatus, StoreOperationalStatus

    run = RunOperationalStatus(
        run_id="c",
        status="healthy",
        store_statuses=[
            StoreOperationalStatus(store_name="st", status="healthy", counters={"delivery_items_total": 1.0}),
        ],
    )
    snap = build_run_diagnostic_snapshot("c", run, [], [])
    missing = REQUIRED_DIAGNOSTIC_KEYS - set(snap)
    assert not missing, missing
