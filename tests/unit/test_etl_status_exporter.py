from __future__ import annotations

from datetime import UTC, datetime

from domain.observability import BatchTraceRecord, ParserHealthSnapshot, SyncCorrelationContext, SyncTraceRecord

from infrastructure.observability.etl_status_exporter import build_etl_status_payload


def test_etl_status_payload_shape():
    health = ParserHealthSnapshot(
        run_id="r1",
        started_at=datetime.now(UTC),
        stores=["st"],
        counters={"crm_rejected_total": 12.0},
        last_errors=[{"x": 1}],
        status="degraded",
    )
    batch = BatchTraceRecord(
        batch_id="b1",
        run_id="r1",
        store_name="st",
        created_at=datetime.now(UTC),
        flushed_at=datetime.now(UTC),
        item_count=3,
        success_count=2,
        rejected_count=1,
        retryable_count=0,
        ignored_count=0,
        transport_failed=False,
        http_status=200,
        notes=["flush"],
    )
    err = SyncTraceRecord(
        stage="crm_apply",
        severity="error",
        message_code="CRM_APPLY_REJECTED",
        correlation=SyncCorrelationContext(run_id="r1", spider_name="s", store_name="st", entity_key="ek"),
    )
    payload = build_etl_status_payload(health, [batch], [err])
    assert payload["run_id"] == "r1"
    assert payload["current_status"] == "degraded"
    assert payload["schema"] == "parser_etl_status_v3"
    assert "crm_rejected_total" in payload["counters_summary"]
    assert payload["last_batch_summaries"][0]["batch_id"] == "b1"
    assert payload["recent_errors"][-1]["message_code"] == "CRM_APPLY_REJECTED"
    assert "degradation_signals" in payload
    assert "dashboard_summary" in payload
    assert "breached_thresholds" in payload
