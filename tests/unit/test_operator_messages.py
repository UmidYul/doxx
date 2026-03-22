from __future__ import annotations

from domain.operational_policy import RunOperationalStatus, StoreOperationalStatus
from domain.operator_support import TriageSummary

from infrastructure.observability.operator_messages import (
    build_human_runbook_message,
    build_human_status_message,
    build_human_triage_message,
)
from infrastructure.observability.runbook_registry import get_runbook_for_domain


def test_human_triage_is_concise_and_actionable():
    s = TriageSummary(
        run_id="r99",
        store_name="shop",
        domain="delivery_transport",
        severity="high",
        suspected_root_cause="delivery_transport degraded due to malformed batch responses",
        evidence=[{"kind": "batch", "batch_id": "b1"}],
        recommended_action="retry_batch_once",
        confidence=0.8,
    )
    msg = build_human_triage_message(s)
    assert "r99" in msg and "shop" in msg
    assert "retry batch once" in msg.lower() or "retry_batch_once" in msg
    assert "malformed" in msg.lower()
    assert "stack" not in msg.lower()


def test_human_runbook_lists_steps():
    p = get_runbook_for_domain("reconciliation", "warning")
    m = build_human_runbook_message(p)
    assert "reconciliation" in m.lower()
    assert "1." in m


def test_human_status_store_and_run():
    st = StoreOperationalStatus(store_name="a", status="degraded", alerts=[], notes=[])
    assert "a" in build_human_status_message(st)
    run = RunOperationalStatus(
        run_id="r1",
        status="degraded",
        store_statuses=[st],
    )
    assert "r1" in build_human_status_message(run)
    assert "triage_run" in build_human_status_message(run).lower()
