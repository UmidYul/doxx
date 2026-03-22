from __future__ import annotations

from config import settings as settings_mod

from infrastructure.observability.dashboard_status import (
    build_run_operational_status,
    build_store_operational_status,
    summarize_status_for_dashboard,
)


def _good_counters() -> dict[str, float]:
    return {
        "product_items_yielded_total": 1000.0,
        "product_parse_failed_total": 5.0,
        "delivery_items_total": 500.0,
        "crm_applied_total": 495.0,
        "listing_pages_seen_total": 200.0,
        "block_pages_total": 1.0,
        "categories_started_total": 20.0,
        "categories_zero_result_total": 1.0,
        "normalization_items_total": 500.0,
        "normalization_low_coverage_total": 10.0,
        "crm_rejected_total": 2.0,
        "crm_retryable_total": 1.0,
        "delivery_batches_total": 50.0,
        "malformed_batch_responses_total": 0.0,
        "reconciliation_started_total": 20.0,
        "reconciliation_failed_total": 0.0,
        "duplicate_payload_skipped_total": 5.0,
    }


def test_one_store_failing_does_not_require_multi_store_global():
    c = _good_counters()
    c["crm_applied_total"] = 10.0
    c["crm_rejected_total"] = 400.0
    run = build_run_operational_status("r1", {"only": c})
    assert run.global_alerts == []
    summ = summarize_status_for_dashboard(run)
    assert summ["overall_status"] in ("degraded", "failing", "healthy")
    assert "only" in summ["per_store_status"]


def test_multi_store_transport_escalates_global(monkeypatch):
    monkeypatch.setattr(settings_mod.settings, "SLO_MAX_MALFORMED_RESPONSE_RATE", 0.01)
    c1 = _good_counters()
    c1["malformed_batch_responses_total"] = 5.0
    c1["delivery_batches_total"] = 10.0
    c2 = dict(c1)
    run = build_run_operational_status("r1", {"a": c1, "b": c2})
    codes = [a.alert_code for a in run.global_alerts]
    assert any("GLOBAL_MULTI_STORE" in x for x in codes)


def test_summarize_includes_worst_breached():
    c = _good_counters()
    st = build_store_operational_status("s", c, "r1")
    summ = summarize_status_for_dashboard(
        build_run_operational_status("r1", {"s": c}),
    )
    assert "worst_breached_thresholds" in summ
    assert "top_incident_domains" in summ
