from __future__ import annotations

from typing import Any

from domain.observability import BatchTraceRecord, ParserHealthSnapshot, SyncTraceRecord

from config.settings import settings
from infrastructure.security.minimizer import minimize_payload_for_support
from infrastructure.security.redaction import redact_payload
from infrastructure.security.support_scope_guard import cap_error_list


def build_etl_status_payload(
    health: ParserHealthSnapshot,
    recent_batches: list[BatchTraceRecord],
    recent_errors: list[SyncTraceRecord],
) -> dict[str, object]:
    """
    Serializer for future CRM ``GET /status`` / ETL dashboard alignment.
    Internal contract only — no HTTP server in this stage.
    """
    counters = dict(health.counters)

    def _batch_summary(b: BatchTraceRecord) -> dict[str, object]:
        return {
            "batch_id": b.batch_id,
            "run_id": b.run_id,
            "store_name": b.store_name,
            "item_count": b.item_count,
            "success_count": b.success_count,
            "rejected_count": b.rejected_count,
            "retryable_count": b.retryable_count,
            "ignored_count": b.ignored_count,
            "transport_failed": b.transport_failed,
            "http_status": b.http_status,
            "notes": list(b.notes),
            "created_at": b.created_at.isoformat() if hasattr(b.created_at, "isoformat") else str(b.created_at),
            "flushed_at": b.flushed_at.isoformat() if b.flushed_at and hasattr(b.flushed_at, "isoformat") else None,
        }

    err_summaries: list[dict[str, object]] = []
    for e in recent_errors[-50:]:
        err_summaries.append(
            {
                "timestamp": e.timestamp.isoformat(),
                "stage": e.stage,
                "severity": e.severity,
                "message_code": e.message_code,
                "failure_domain": e.failure_domain,
                "failure_type": e.failure_type,
                "entity_key": e.correlation.entity_key,
                "event_id": e.correlation.event_id,
                "batch_id": e.correlation.batch_id,
            }
        )

    err_summaries = cap_error_list(err_summaries, settings)
    critical_recent = [x for x in err_summaries if x.get("severity") in ("critical", "error")][-20:]

    err_by_dom = dict(health.error_aggregates_by_domain or {})
    dash = dict(health.dashboard_summary or {})

    degradation_signals: list[str] = []
    if float(counters.get("crawl_failures_total", 0) or 0) >= 10:
        degradation_signals.append("high_crawl_failures")
    if float(counters.get("block_pages_total", 0) or 0) >= 2:
        degradation_signals.append("block_pages")
    if float(counters.get("delivery_retries_total", 0) or 0) >= 10:
        degradation_signals.append("transport_retries")
    if float(counters.get("crm_rejected_total", 0) or 0) >= 10:
        degradation_signals.append("crm_rejections")
    if float(counters.get("reconciliation_failed_total", 0) or 0) >= 2:
        degradation_signals.append("reconciliation_unresolved")
    if float(counters.get("normalization_low_coverage_total", 0) or 0) >= 10:
        degradation_signals.append("low_spec_coverage")
    if health.status == "degraded":
        degradation_signals.append("health_degraded")
    if health.status == "failing":
        degradation_signals.append("health_failing")

    top_alerts = list(health.operational_alerts)[-25:]
    breached = [d for d in health.threshold_decisions if d.get("breached")]
    breached.sort(key=lambda x: float(x.get("observed_value") or 0), reverse=True)

    op = dict(health.operator_support or {})
    triage_run = op.get("triage_run") if isinstance(op.get("triage_run"), dict) else {}
    diag_run = op.get("diagnostic_run") if isinstance(op.get("diagnostic_run"), dict) else {}

    payload: dict[str, object] = {
        "schema": "parser_etl_status_v3",
        "enabled": bool(getattr(settings, "ENABLE_ETL_STATUS_EXPORT", True)),
        "run_id": health.run_id,
        "current_status": health.status,
        "started_at": health.started_at.isoformat(),
        "stores": list(health.stores),
        "counters_summary": counters,
        "last_batch_summaries": [_batch_summary(b) for b in recent_batches[-20:]],
        "last_critical_errors": critical_recent,
        "recent_errors": err_summaries,
        "errors_by_domain": err_by_dom,
        "degradation_signals": degradation_signals,
        "last_errors_embedded": list(health.last_errors),
        # --- 5B operational policy ---
        "dashboard_summary": dash,
        "top_operational_alerts": top_alerts,
        "breached_thresholds": breached[:20],
        "recommended_run_action": dash.get("recommended_run_action"),
        "recommended_per_store": dash.get("recommended_per_store"),
        "serialized_run_operational": dict(health.serialized_run_operational or {}),
        # --- 5C operator support (compact; no raw payloads) ---
        "operator_support": op,
        "triage_summary": triage_run,
        "recommended_operator_action": triage_run.get("recommended_action") or dash.get("recommended_operator_action"),
        "runbook_domain": triage_run.get("domain") or dash.get("operator_triage_domain"),
        "runbook_plan": op.get("runbook"),
        "diagnostic_snapshot": diag_run,
        "operator_headline": dash.get("operator_headline"),
    }
    from application.release.shape_compat import apply_export_compatibility

    from infrastructure.security import data_governance_logger as dg_log

    compat = apply_export_compatibility("etl_status", payload)
    red = redact_payload(compat)
    if getattr(settings, "ENABLE_DATA_MINIMIZATION", True):
        out = minimize_payload_for_support(red, settings, purpose="observability")
        if getattr(settings, "ENABLE_SAFE_DIAGNOSTIC_EXPORTS", True):
            dg_log.emit_diagnostic_export_minimized(artifact_name="etl_status", kept_fields_count=len(out))
        return out
    return red
