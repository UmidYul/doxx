from __future__ import annotations

from datetime import UTC, datetime

from domain.observability import BatchTraceRecord, SyncCorrelationContext, SyncTraceRecord
from domain.operational_policy import AlertSignal, RunOperationalStatus, StoreOperationalStatus

from infrastructure.observability.triage_engine import (
    build_triage_summary_for_run,
    build_triage_summary_for_store,
    collect_support_evidence,
    infer_root_cause,
)


def _corr(run_id: str = "r1", store: str = "st") -> SyncCorrelationContext:
    return SyncCorrelationContext(run_id=run_id, spider_name="sp", store_name=store)


def _alert(domain: str, sev: str = "high", code: str = "T") -> AlertSignal:
    return AlertSignal(
        alert_code=code,
        severity=sev,  # type: ignore[arg-type]
        domain=domain,  # type: ignore[arg-type]
        run_id="r1",
        message="m",
    )


def test_block_page_spike_store_access_triage(monkeypatch):
    monkeypatch.setattr("infrastructure.observability.triage_engine.settings.ENABLE_OPERATOR_TRIAGE_SUMMARY", True)
    tr = [
        SyncTraceRecord(
            stage="crawl",
            severity="error",
            message_code="CRAWL_FAILURE",
            correlation=_corr(),
            failure_domain="anti_bot",
            failure_type="block_page",
        )
    ]
    ss = StoreOperationalStatus(
        store_name="st",
        status="degraded",
        alerts=[_alert("store_access")],
    )
    bt: list[BatchTraceRecord] = []
    summ = build_triage_summary_for_store("r1", ss, tr, bt)
    assert summ.domain == "store_access"
    assert "block page" in summ.suspected_root_cause.lower()
    ev = collect_support_evidence(tr, bt, limit=10)
    assert any(e.get("failure_type") == "block_page" for e in ev if e.get("kind") == "trace")


def test_malformed_batch_delivery_transport(monkeypatch):
    monkeypatch.setattr("infrastructure.observability.triage_engine.settings.ENABLE_OPERATOR_TRIAGE_SUMMARY", True)
    tr: list[SyncTraceRecord] = []
    bt = [
        BatchTraceRecord(
            batch_id="b1",
            run_id="r1",
            store_name="st",
            created_at=datetime.now(UTC),
            transport_failed=True,
            notes=["malformed JSON from CRM"],
        )
    ]
    ss = StoreOperationalStatus(
        store_name="st",
        status="degraded",
        alerts=[_alert("delivery_transport")],
    )
    summ = build_triage_summary_for_store("r1", ss, tr, bt)
    assert summ.domain == "delivery_transport"
    assert "malformed" in summ.suspected_root_cause.lower()


def test_rejected_item_surge_crm_apply(monkeypatch):
    monkeypatch.setattr("infrastructure.observability.triage_engine.settings.ENABLE_OPERATOR_TRIAGE_SUMMARY", True)
    tr = [
        SyncTraceRecord(
            stage="crm_apply",
            severity="error",
            message_code="CRM_APPLY_REJECTED",
            correlation=_corr(),
        )
        for _ in range(5)
    ]
    ss = StoreOperationalStatus(store_name="st", status="failing", alerts=[_alert("crm_apply", "critical")])
    summ = build_triage_summary_for_store("r1", ss, tr, [])
    assert summ.domain == "crm_apply"
    assert "reject" in summ.suspected_root_cause.lower()
    assert summ.recommended_action == "downgrade_to_product_found"


def test_unresolved_reconciliation_domain(monkeypatch):
    monkeypatch.setattr("infrastructure.observability.triage_engine.settings.ENABLE_OPERATOR_TRIAGE_SUMMARY", True)
    tr = [
        SyncTraceRecord(
            stage="reconcile",
            severity="warning",
            message_code="RECONCILIATION_UNRESOLVED",
            correlation=_corr(),
        )
    ]
    run = RunOperationalStatus(
        run_id="r1",
        status="degraded",
        store_statuses=[
            StoreOperationalStatus(store_name="st", status="healthy"),
        ],
        global_alerts=[],
    )
    # force reconciliation via infer on traces
    cause = infer_root_cause("reconciliation", tr, [], [])
    assert "unresolved" in cause.lower()
    ss_bad = StoreOperationalStatus(
        store_name="st",
        status="degraded",
        alerts=[_alert("reconciliation")],
    )
    summ = build_triage_summary_for_store("r1", ss_bad, tr, [])
    assert summ.domain == "reconciliation"


def test_infer_root_cause_uses_thresholds():
    cause = infer_root_cause("internal", [], [], [{"metric_name": "x", "breached": True}])
    assert "x" in cause
