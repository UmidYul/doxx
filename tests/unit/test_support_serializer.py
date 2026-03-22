from __future__ import annotations

from domain.operator_support import TriageSummary

from infrastructure.observability.support_serializer import (
    serialize_diagnostic_snapshot,
    serialize_runbook,
    serialize_triage_summary,
)
from infrastructure.observability.runbook_registry import get_runbook_for_domain


def test_serialize_triage_strips_noisy_evidence_keys():
    s = TriageSummary(
        run_id="r1",
        store_name="st",
        domain="internal",
        severity="warning",
        suspected_root_cause="x",
        evidence=[{"kind": "trace", "details": "SECRET", "stage": "crawl"}],
        recommended_action="continue",
        confidence=0.7,
    )
    out = serialize_triage_summary(s)
    row = out["evidence"][0]
    assert "details" not in row
    assert row.get("stage") == "crawl"


def test_serialize_diagnostic_omits_noisy_keys():
    snap = {
        "top_alerts": [{"alert_code": "A", "details": "NO"}],
        "recent_failed_items_sample": [{"stage": "x"}],
    }
    ser = serialize_diagnostic_snapshot(snap)
    assert "details" not in ser["top_alerts"][0]


def test_serialize_runbook_roundtrip_keys():
    p = get_runbook_for_domain("crm_apply", "high")
    d = serialize_runbook(p)
    assert d["domain"] == "crm_apply"
    assert d["steps"]
