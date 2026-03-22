from __future__ import annotations

from datetime import UTC, datetime

from domain.observability import BatchTraceRecord, SyncCorrelationContext, SyncTraceRecord
from domain.operational_policy import AlertSignal, RunOperationalStatus, StoreOperationalStatus

from infrastructure.observability.diagnostic_snapshot import (
    build_run_diagnostic_snapshot,
    build_store_diagnostic_snapshot,
)


def _corr(store: str = "st") -> SyncCorrelationContext:
    return SyncCorrelationContext(run_id="r1", spider_name="sp", store_name=store)


def test_diagnostic_snapshot_top_alerts_and_recommended_action(monkeypatch):
    monkeypatch.setattr(
        "infrastructure.observability.diagnostic_snapshot.settings.ENABLE_DIAGNOSTIC_SNAPSHOTS",
        True,
    )
    monkeypatch.setattr(
        "infrastructure.observability.diagnostic_snapshot.settings.ENABLE_OPERATOR_TRIAGE_SUMMARY",
        True,
    )
    tr = [
        SyncTraceRecord(
            stage="crm_apply",
            severity="error",
            message_code="CRM_APPLY_REJECTED",
            correlation=_corr(),
        )
    ]
    alert = AlertSignal(
        alert_code="R",
        severity="high",
        domain="crm_apply",
        run_id="r1",
        store_name="st",
        message="m",
    )
    ss = StoreOperationalStatus(
        store_name="st",
        status="degraded",
        alerts=[alert],
        counters={"crm_rejected_total": 50.0, "delivery_items_total": 100.0},
    )
    run = RunOperationalStatus(run_id="r1", status="degraded", store_statuses=[ss])
    snap = build_run_diagnostic_snapshot("r1", run, tr, [])
    assert snap["top_alerts"]
    assert snap["recommended_action"]
    assert snap["runbook_domain"] == "crm_apply"
    assert "recent_rejected_items_sample" in snap

    st_snap = build_store_diagnostic_snapshot(
        "st",
        "r1",
        tr,
        [],
        {"crm_rejected_total": 50.0, "delivery_items_total": 100.0},
        [alert.model_dump(mode="json")],
    )
    assert st_snap["store_name"] == "st"
    assert st_snap["top_alerts"]


def test_malformed_batches_surface(monkeypatch):
    monkeypatch.setattr(
        "infrastructure.observability.diagnostic_snapshot.settings.ENABLE_DIAGNOSTIC_SNAPSHOTS",
        True,
    )
    monkeypatch.setattr(
        "infrastructure.observability.diagnostic_snapshot.settings.ENABLE_OPERATOR_TRIAGE_SUMMARY",
        True,
    )
    bt = [
        BatchTraceRecord(
            batch_id="b9",
            run_id="r1",
            store_name="st",
            created_at=datetime.now(UTC),
            notes=["malformed"],
        )
    ]
    run = RunOperationalStatus(
        run_id="r1",
        status="healthy",
        store_statuses=[StoreOperationalStatus(store_name="st", status="healthy", counters={"delivery_items_total": 1.0})],
    )
    snap = build_run_diagnostic_snapshot("r1", run, [], bt)
    assert snap.get("last_malformed_batches")
