from __future__ import annotations

from collections import Counter

from domain.operational_policy import AlertSeverity, AlertSignal, RunOperationalStatus, ServiceStatus, StoreOperationalStatus

from infrastructure.observability.alert_policy import build_alerts_from_thresholds
from infrastructure.observability.threshold_evaluator import (
    decide_status_from_thresholds,
    evaluate_run_thresholds,
    evaluate_store_thresholds,
)


def _worst_status(a: ServiceStatus, b: ServiceStatus) -> ServiceStatus:
    order = ("healthy", "degraded", "failing")
    return a if order.index(a) >= order.index(b) else b


def build_store_operational_status(store_name: str, counters: dict[str, int | float], run_id: str) -> StoreOperationalStatus:
    decisions = evaluate_store_thresholds(store_name, counters)
    status = decide_status_from_thresholds(decisions)
    alerts = build_alerts_from_thresholds(run_id, store_name, decisions)
    notes: list[str] = []
    if not counters.get("delivery_items_total"):
        notes.append("no_delivery_items_in_scope")
    return StoreOperationalStatus(
        store_name=store_name,
        status=status,
        alerts=alerts,
        breached_thresholds=[d for d in decisions if d.breached],
        counters=dict(counters),
        notes=notes,
    )


def build_run_operational_status(
    run_id: str,
    store_counters: dict[str, dict[str, int | float]],
) -> RunOperationalStatus:
    store_statuses: list[StoreOperationalStatus] = []
    for store_name, ctr in sorted(store_counters.items()):
        store_statuses.append(build_store_operational_status(store_name, ctr, run_id))

    merged: dict[str, int | float] = {}
    for ctr in store_counters.values():
        for k, v in ctr.items():
            merged[k] = merged.get(k, 0) + (float(v) if isinstance(v, (int, float)) else 0.0)

    run_decisions = evaluate_run_thresholds(merged)
    run_status: ServiceStatus = decide_status_from_thresholds(run_decisions)
    global_alerts: list[AlertSignal] = []

    transport_stores = sum(
        1
        for ss in store_statuses
        if any(a.domain == "delivery_transport" and a.severity in ("high", "critical") for a in ss.alerts)
    )
    crm_stores = sum(
        1
        for ss in store_statuses
        if any(a.domain == "crm_apply" and a.severity in ("high", "critical") for a in ss.alerts)
    )
    n_stores = len(store_statuses)
    if n_stores >= 2 and transport_stores >= 2:
        global_alerts.append(
            AlertSignal(
                alert_code="GLOBAL_MULTI_STORE_TRANSPORT_STRESS",
                severity="high",
                domain="delivery_transport",
                store_name=None,
                run_id=run_id,
                metric_name=None,
                observed_value=float(transport_stores),
                threshold_value=2.0,
                message=f"{transport_stores} stores show transport/apply delivery stress",
                tags={"kind": "global_candidate"},
            )
        )
    if n_stores >= 2 and crm_stores >= 2:
        global_alerts.append(
            AlertSignal(
                alert_code="GLOBAL_MULTI_STORE_CRM_APPLY_STRESS",
                severity="high",
                domain="crm_apply",
                store_name=None,
                run_id=run_id,
                metric_name=None,
                observed_value=float(crm_stores),
                threshold_value=2.0,
                message=f"{crm_stores} stores show CRM apply stress",
                tags={"kind": "global_candidate"},
            )
        )

    notes: list[str] = []
    for ss in store_statuses:
        run_status = _worst_status(run_status, ss.status)
    if global_alerts:
        ga_sev = max((a.severity for a in global_alerts), key=_sev_key)
        if ga_sev == "critical":
            run_status = _worst_status(run_status, "failing")
        elif ga_sev == "high":
            run_status = _worst_status(run_status, "degraded")

    return RunOperationalStatus(
        run_id=run_id,
        status=run_status,
        store_statuses=store_statuses,
        global_alerts=global_alerts,
        notes=notes,
    )


def _sev_key(s: AlertSeverity) -> int:
    return {"info": 0, "warning": 1, "high": 2, "critical": 3}.get(s, 0)


def summarize_status_for_dashboard(status: RunOperationalStatus) -> dict[str, object]:
    crit = sum(1 for ss in status.store_statuses for a in ss.alerts if a.severity == "critical")
    crit += sum(1 for a in status.global_alerts if a.severity == "critical")
    warn = sum(1 for ss in status.store_statuses for a in ss.alerts if a.severity == "warning")
    warn += sum(1 for a in status.global_alerts if a.severity == "warning")
    high = sum(1 for ss in status.store_statuses for a in ss.alerts if a.severity == "high")
    high += sum(1 for a in status.global_alerts if a.severity == "high")

    domains: Counter[str] = Counter()
    for ss in status.store_statuses:
        for a in ss.alerts:
            domains[a.domain] += 1
    for a in status.global_alerts:
        domains[a.domain] += 1

    worst: list[dict[str, object]] = []
    for ss in status.store_statuses:
        for d in ss.breached_thresholds:
            worst.append(
                {
                    "store_name": ss.store_name,
                    "metric_name": d.metric_name,
                    "observed_value": d.observed_value,
                    "threshold_value": d.threshold_value,
                    "severity": d.severity,
                }
            )
    worst.sort(key=lambda x: float(x.get("observed_value") or 0), reverse=True)

    degradation_signals: list[str] = []
    if status.status != "healthy":
        degradation_signals.append(f"run_status_{status.status}")
    for ss in status.store_statuses:
        if ss.status != "healthy":
            degradation_signals.append(f"store_{ss.store_name}_{ss.status}")

    baseline_hint: str | None = None
    worst_rank = -1
    for ss in status.store_statuses:
        for a in ss.alerts:
            r = _sev_key(a.severity)
            if r > worst_rank:
                worst_rank = r
                baseline_hint = f"{a.domain}:{a.alert_code} (store={ss.store_name})"
    for a in status.global_alerts:
        r = _sev_key(a.severity)
        if r > worst_rank:
            worst_rank = r
            baseline_hint = f"{a.domain}:{a.alert_code} (global)"

    return {
        "overall_status": status.status,
        "per_store_status": {ss.store_name: ss.status for ss in status.store_statuses},
        "critical_alerts_count": crit,
        "warning_alerts_count": warn,
        "high_alerts_count": high,
        "top_incident_domains": domains.most_common(8),
        "worst_breached_thresholds": worst[:15],
        "recent_degradation_signals": degradation_signals[:20],
        "global_alerts_count": len(status.global_alerts),
        # 5C: short hint even before trace_collector merges triage headline
        "operator_baseline_hint": baseline_hint,
    }


def aggregate_errors_by_domain(recent_errors: list[dict[str, object]]) -> dict[str, dict[str, int]]:
    """Roll up trace-derived errors by failure_domain and severity."""
    by_dom: dict[str, dict[str, int]] = {}
    for e in recent_errors:
        dom = str(e.get("failure_domain") or "unknown")
        sev = str(e.get("severity") or "unknown")
        by_dom.setdefault(dom, {})
        by_dom[dom][sev] = by_dom[dom].get(sev, 0) + 1
    return by_dom
