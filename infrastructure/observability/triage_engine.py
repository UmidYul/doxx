from __future__ import annotations

from collections import Counter

from domain.observability import BatchTraceRecord, SyncTraceRecord
from domain.operational_policy import RunOperationalStatus, StoreOperationalStatus
from domain.operator_support import RunbookAction, TriageDomain, TriageSummary

from config.settings import settings
from infrastructure.observability.incident_classifier import classify_run_incident, classify_store_incident
from infrastructure.observability.store_control import suggest_run_action, suggest_store_action


def _as_domain(v: str | None) -> TriageDomain:
    allowed: tuple[TriageDomain, ...] = (
        "store_access",
        "crawl_quality",
        "normalization_quality",
        "delivery_transport",
        "crm_apply",
        "reconciliation",
        "internal",
    )
    if v in allowed:
        return v  # type: ignore[return-value]
    return "internal"


def _severity_from_store(ss: StoreOperationalStatus) -> str:
    if ss.status == "failing":
        return "critical"
    if ss.status == "degraded":
        return "high"
    for a in ss.alerts:
        if a.severity == "critical":
            return "critical"
    for a in ss.alerts:
        if a.severity == "high":
            return "high"
    return "warning"


def _severity_from_run(rs: RunOperationalStatus) -> str:
    if rs.status == "failing":
        return "critical"
    if rs.status == "degraded":
        return "high"
    for a in rs.global_alerts:
        if a.severity == "critical":
            return "critical"
    for ss in rs.store_statuses:
        s = _severity_from_store(ss)
        if s == "critical":
            return "critical"
    for ss in rs.store_statuses:
        if _severity_from_store(ss) == "high":
            return "high"
    return "warning"


def collect_support_evidence(
    traces: list[SyncTraceRecord],
    batches: list[BatchTraceRecord],
    *,
    limit: int = 10,
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    n_trace = max(1, limit // 2)
    n_batch = limit - n_trace
    for r in traces[-80:]:
        if r.severity not in ("error", "critical", "warning"):
            continue
        out.append(
            {
                "kind": "trace",
                "stage": r.stage,
                "message_code": r.message_code,
                "severity": r.severity,
                "failure_domain": r.failure_domain,
                "failure_type": r.failure_type,
                "store": r.correlation.store_name,
                "entity_key": r.correlation.entity_key,
                "batch_id": r.correlation.batch_id,
            }
        )
        if len(out) >= n_trace:
            break
    for b in batches[-15:]:
        if len(out) >= limit:
            break
        if b.transport_failed or b.rejected_count or b.retryable_count:
            out.append(
                {
                    "kind": "batch",
                    "batch_id": b.batch_id,
                    "store_name": b.store_name,
                    "transport_failed": b.transport_failed,
                    "http_status": b.http_status,
                    "rejected_count": b.rejected_count,
                    "retryable_count": b.retryable_count,
                    "notes": b.notes[:3],
                }
            )
    return out[:limit]


def infer_root_cause(
    domain: TriageDomain,
    traces: list[SyncTraceRecord],
    batches: list[BatchTraceRecord],
    thresholds: list[dict[str, object]],
) -> str:
    codes = [t.message_code for t in traces[-40:]]
    code_cnt = Counter(codes)
    top_code = code_cnt.most_common(1)[0][0] if code_cnt else ""

    if domain == "store_access":
        if any(t.failure_type == "block_page" for t in traces[-30:]):
            return "store_access degraded due to block page / anti-bot spike"
        if any("block" in str(t.message_code).lower() for t in traces[-20:]):
            return "store_access degraded due to elevated block or access signals"
        return "store_access degraded — verify listing/PDP reachability and store profile"

    if domain == "crawl_quality":
        if top_code == "CRAWL_FAILURE":
            return "crawl_quality degraded due to crawl failures (network/parse/scheduler)"
        if top_code == "CRAWL_PRODUCT_PARTIAL":
            return "crawl_quality degraded due to partial product ratio"
        return "crawl_quality degraded — inspect parse success SLO vs failures"

    if domain == "normalization_quality":
        return "normalization_quality degraded due to low mapping coverage or spec warnings cluster"

    if domain == "delivery_transport":
        mal_batches = sum(1 for b in batches[-20:] if b.transport_failed or any("malformed" in str(n).lower() for n in b.notes))
        if mal_batches:
            return "delivery_transport degraded due to malformed batch responses or transport failures"
        if any(t.message_code == "DELIVERY_RETRY" for t in traces[-30:]):
            return "delivery_transport degraded due to CRM HTTP retry pressure"
        return "delivery_transport degraded — inspect batch flush and HTTP retry traces"

    if domain == "crm_apply":
        rej = sum(1 for t in traces[-40:] if t.message_code == "CRM_APPLY_REJECTED")
        if rej >= 3:
            return "crm_apply degraded due to rejected item surge (validation/business rules)"
        if any(t.message_code == "CRM_APPLY_RETRYABLE" for t in traces[-20:]):
            return "crm_apply stress with retryable items — check transient CRM health"
        return "crm_apply degraded — separate rejects vs retryables in traces"

    if domain == "reconciliation":
        if any(t.message_code == "RECONCILIATION_UNRESOLVED" for t in traces[-30:]):
            return "reconciliation degraded due to unresolved RECONCILIATION_UNRESOLVED events"
        return "reconciliation degraded — missing_ids or ambiguous CRM apply signals"

    breached_names = [str(x.get("metric_name")) for x in thresholds if x.get("breached")]
    if breached_names:
        return f"internal/threshold signals: {', '.join(breached_names[:4])}"
    return "internal — correlate run_id with CRM audit; no dominant domain signal"


def _store_to_runbook(sug: str, domain: TriageDomain) -> RunbookAction:
    if domain == "reconciliation":
        return "replay_product_found"
    if domain == "delivery_transport":
        return "retry_batch_once"
    if sug == "disable_store" and settings.ENABLE_STORE_DISABLE_ADVICE:
        return "disable_store_temporarily"
    if sug == "degrade":
        return "investigate_manually"
    if sug == "fail_run":
        return "fail_run"
    return "continue"


def _run_to_runbook(sug: str, domain: TriageDomain) -> RunbookAction:
    if sug == "fail_run":
        return "fail_run"
    if sug == "degrade":
        if domain == "delivery_transport":
            return "retry_batch_once"
        return "investigate_manually"
    return "continue"


def _confidence(evidence_n: int, has_alerts: bool) -> float:
    base = 0.55
    base += min(0.35, 0.05 * evidence_n)
    if has_alerts:
        base += 0.05
    return round(min(0.95, base), 2)


def build_triage_summary_for_store(
    run_id: str,
    store_status: StoreOperationalStatus,
    recent_traces: list[SyncTraceRecord],
    recent_batches: list[BatchTraceRecord],
) -> TriageSummary:
    if not settings.ENABLE_OPERATOR_TRIAGE_SUMMARY:
        return TriageSummary(
            run_id=run_id,
            store_name=store_status.store_name,
            domain="internal",
            severity="info",
            suspected_root_cause="operator triage disabled",
            evidence=[],
            recommended_action="continue",
            confidence=0.5,
        )

    inc = classify_store_incident(store_status)
    if inc:
        dom = _as_domain(inc)
    elif store_status.alerts:
        dom = _as_domain(store_status.alerts[0].domain)
    else:
        dom = "internal"
    sev = _severity_from_store(store_status)
    store_tr = [t for t in recent_traces if t.correlation.store_name == store_status.store_name]
    store_bt = [b for b in recent_batches if b.store_name == store_status.store_name]
    thr = [d.model_dump(mode="json") for d in store_status.breached_thresholds]
    cause = infer_root_cause(dom, store_tr, store_bt, thr)
    ev = collect_support_evidence(store_tr, store_bt, limit=settings.DIAGNOSTIC_ERROR_SAMPLE_SIZE)
    sug = suggest_store_action(store_status)
    action = _store_to_runbook(sug, dom)
    if dom == "crm_apply" and store_status.status == "failing":
        action = "downgrade_to_product_found"
    return TriageSummary(
        run_id=run_id,
        store_name=store_status.store_name,
        domain=dom,
        severity=sev,
        suspected_root_cause=cause,
        evidence=ev,
        recommended_action=action,
        confidence=_confidence(len(ev), bool(store_status.alerts)),
    )


def build_triage_summary_for_run(
    run_status: RunOperationalStatus,
    recent_traces: list[SyncTraceRecord],
    recent_batches: list[BatchTraceRecord],
) -> TriageSummary:
    if not settings.ENABLE_OPERATOR_TRIAGE_SUMMARY:
        return TriageSummary(
            run_id=run_status.run_id,
            store_name=None,
            domain="internal",
            severity="info",
            suspected_root_cause="operator triage disabled",
            evidence=[],
            recommended_action="continue",
            confidence=0.5,
        )

    rinc = classify_run_incident(run_status)
    if rinc:
        dom = _as_domain(rinc)
    elif run_status.global_alerts:
        dom = _as_domain(run_status.global_alerts[0].domain)
    elif run_status.store_statuses and run_status.store_statuses[0].alerts:
        dom = _as_domain(run_status.store_statuses[0].alerts[0].domain)
    else:
        dom = "internal"
    sev = _severity_from_run(run_status)
    thr: list[dict[str, object]] = []
    for ss in run_status.store_statuses:
        for d in ss.breached_thresholds:
            thr.append(d.model_dump(mode="json"))
    cause = infer_root_cause(dom, recent_traces, recent_batches, thr)
    ev = collect_support_evidence(recent_traces, recent_batches, limit=settings.DIAGNOSTIC_ERROR_SAMPLE_SIZE)
    sug = suggest_run_action(run_status)
    action = _run_to_runbook(sug, dom)
    has_alerts = bool(run_status.global_alerts) or any(ss.alerts for ss in run_status.store_statuses)
    return TriageSummary(
        run_id=run_status.run_id,
        store_name=None,
        domain=dom,
        severity=sev,
        suspected_root_cause=cause,
        evidence=ev,
        recommended_action=action,
        confidence=_confidence(len(ev), has_alerts),
    )
