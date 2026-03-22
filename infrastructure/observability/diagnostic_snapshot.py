from __future__ import annotations

from config.settings import settings
from domain.observability import BatchTraceRecord, SyncTraceRecord
from domain.operational_policy import RunOperationalStatus

from infrastructure.observability.dashboard_status import build_store_operational_status
from infrastructure.observability.triage_engine import build_triage_summary_for_run, build_triage_summary_for_store


def _compact_trace(t: SyncTraceRecord) -> dict[str, object]:
    return {
        "stage": t.stage,
        "message_code": t.message_code,
        "severity": t.severity,
        "failure_domain": t.failure_domain,
        "failure_type": t.failure_type,
        "entity_key": t.correlation.entity_key,
        "batch_id": t.correlation.batch_id,
    }


def _severity_rank(s: str) -> int:
    return {"info": 0, "warning": 1, "high": 2, "critical": 3}.get(s.lower(), 0)


def build_store_diagnostic_snapshot(
    store_name: str,
    run_id: str,
    traces: list[SyncTraceRecord],
    batches: list[BatchTraceRecord],
    counters: dict[str, int | float],
    alerts: list[dict[str, object]],
) -> dict[str, object]:
    """Compact, support-oriented view for one store (no raw payloads)."""
    if not settings.ENABLE_DIAGNOSTIC_SNAPSHOTS:
        return {"enabled": False, "store_name": store_name, "run_id": run_id}

    n = int(settings.DIAGNOSTIC_ERROR_SAMPLE_SIZE)
    store_tr = [t for t in traces if t.correlation.store_name == store_name]
    store_bt = [b for b in batches if b.store_name == store_name]

    ss = build_store_operational_status(store_name, dict(counters), run_id)
    triage = build_triage_summary_for_store(run_id, ss, store_tr, store_bt)

    rel_alerts = [a for a in alerts if a.get("store_name") in (store_name, None, "*")]
    rel_alerts.sort(key=lambda x: _severity_rank(str(x.get("severity") or "")), reverse=True)
    top_alerts = rel_alerts[:8]

    failed = [_compact_trace(t) for t in store_tr if t.severity in ("error", "critical")][-n:]
    rejected = [_compact_trace(t) for t in store_tr if t.message_code == "CRM_APPLY_REJECTED"][-n:]
    retryable = [_compact_trace(t) for t in store_tr if t.message_code == "CRM_APPLY_RETRYABLE"][-n:]
    malformed_t = [_compact_trace(t) for t in store_tr if t.failure_type == "malformed_response"][-5:]
    malformed_b: list[dict[str, object]] = []
    for b in store_bt[-10:]:
        if b.transport_failed or any("malformed" in str(x).lower() for x in b.notes):
            malformed_b.append(
                {
                    "batch_id": b.batch_id,
                    "http_status": b.http_status,
                    "transport_failed": b.transport_failed,
                    "notes": list(b.notes)[:3],
                }
            )
    malformed_b = malformed_b[-5:]

    unresolved = [_compact_trace(t) for t in store_tr if t.message_code == "RECONCILIATION_UNRESOLVED"][-n:]

    snap = {
        "kind": "store",
        "run_id": run_id,
        "store_name": store_name,
        "current_status": ss.status,
        "top_alerts": top_alerts,
        "recent_failed_items_sample": failed,
        "recent_rejected_items_sample": rejected,
        "recent_retryable_items_sample": retryable,
        "last_malformed_traces": malformed_t,
        "last_malformed_batches": malformed_b,
        "last_unresolved_reconciliations": unresolved,
        "recommended_action": triage.recommended_action,
        "runbook_domain": triage.domain,
        "suspected_root_cause": triage.suspected_root_cause,
    }
    if getattr(settings, "ENABLE_DATA_MINIMIZATION", True) and getattr(settings, "ENABLE_SAFE_DIAGNOSTIC_EXPORTS", True):
        from infrastructure.security.minimizer import minimize_diagnostic_snapshot

        return minimize_diagnostic_snapshot(snap, settings)  # type: ignore[return-value]
    return snap


def build_run_diagnostic_snapshot(
    run_id: str,
    statuses: RunOperationalStatus,
    traces: list[SyncTraceRecord],
    batches: list[BatchTraceRecord],
) -> dict[str, object]:
    """Run-level diagnostic rollup (no raw payloads)."""
    if not settings.ENABLE_DIAGNOSTIC_SNAPSHOTS:
        return {"enabled": False, "run_id": run_id}

    n = int(settings.DIAGNOSTIC_ERROR_SAMPLE_SIZE)
    triage = build_triage_summary_for_run(statuses, traces, batches)

    merged: dict[str, int | float] = {}
    for ss in statuses.store_statuses:
        for k, v in ss.counters.items():
            merged[k] = merged.get(k, 0) + (float(v) if isinstance(v, (int, float)) else 0.0)

    all_alerts: list[dict[str, object]] = []
    for ss in statuses.store_statuses:
        for a in ss.alerts:
            all_alerts.append(a.model_dump(mode="json"))
    for a in statuses.global_alerts:
        all_alerts.append(a.model_dump(mode="json"))
    all_alerts.sort(key=lambda x: _severity_rank(str(x.get("severity") or "")), reverse=True)
    top_alerts = all_alerts[:12]

    failed = [_compact_trace(t) for t in traces if t.severity in ("error", "critical")][-n:]
    rejected = [_compact_trace(t) for t in traces if t.message_code == "CRM_APPLY_REJECTED"][-n:]
    retryable = [_compact_trace(t) for t in traces if t.message_code == "CRM_APPLY_RETRYABLE"][-n:]
    malformed_t = [_compact_trace(t) for t in traces if t.failure_type == "malformed_response"][-5:]
    malformed_b: list[dict[str, object]] = []
    for b in batches[-15:]:
        if b.transport_failed or any("malformed" in str(x).lower() for x in b.notes):
            malformed_b.append(
                {
                    "batch_id": b.batch_id,
                    "store_name": b.store_name,
                    "http_status": b.http_status,
                    "transport_failed": b.transport_failed,
                    "notes": list(b.notes)[:3],
                }
            )
    malformed_b = malformed_b[-5:]
    unresolved = [_compact_trace(t) for t in traces if t.message_code == "RECONCILIATION_UNRESOLVED"][-n:]

    snap = {
        "kind": "run",
        "run_id": run_id,
        "current_status": statuses.status,
        "top_alerts": top_alerts,
        "recent_failed_items_sample": failed,
        "recent_rejected_items_sample": rejected,
        "recent_retryable_items_sample": retryable,
        "last_malformed_traces": malformed_t,
        "last_malformed_batches": malformed_b,
        "last_unresolved_reconciliations": unresolved,
        "recommended_action": triage.recommended_action,
        "runbook_domain": triage.domain,
        "suspected_root_cause": triage.suspected_root_cause,
        "counters_merged_summary": {k: merged[k] for k in sorted(merged)[:40]},
    }
    if getattr(settings, "ENABLE_DATA_MINIMIZATION", True) and getattr(settings, "ENABLE_SAFE_DIAGNOSTIC_EXPORTS", True):
        from infrastructure.security.minimizer import minimize_diagnostic_snapshot

        return minimize_diagnostic_snapshot(snap, settings)  # type: ignore[return-value]
    return snap
