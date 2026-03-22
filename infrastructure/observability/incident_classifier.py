from __future__ import annotations

from collections import Counter

from config.settings import settings
from domain.operational_policy import IncidentDomain, RunOperationalStatus, StoreOperationalStatus


def classify_store_incident(status: StoreOperationalStatus) -> IncidentDomain | None:
    if status.status == "healthy":
        return None
    crit = [a for a in status.alerts if a.severity == "critical"]
    if crit:
        return crit[0].domain
    high = [a for a in status.alerts if a.severity == "high"]
    if high:
        c = Counter(a.domain for a in high)
        return c.most_common(1)[0][0]
    if status.alerts:
        c = Counter(a.domain for a in status.alerts)
        return c.most_common(1)[0][0]
    return "internal"


def classify_run_incident(status: RunOperationalStatus) -> IncidentDomain | None:
    if status.status == "healthy":
        return None
    if status.global_alerts:
        ga = max(status.global_alerts, key=lambda a: _sev_rank(a.severity))
        return ga.domain
    doms = [classify_store_incident(ss) for ss in status.store_statuses if ss.status != "healthy"]
    doms = [d for d in doms if d]
    if not doms:
        return "internal"
    c = Counter(doms)
    return c.most_common(1)[0][0]


def _sev_rank(s: str) -> int:
    return {"info": 0, "warning": 1, "high": 2, "critical": 3}.get(s, 0)


def should_disable_store(status: StoreOperationalStatus) -> bool:
    if not settings.INCIDENT_DISABLE_STORE_ON_CRITICAL_STORE_ALERT:
        return False
    return bool(status.alerts) and any(a.severity == "critical" for a in status.alerts)


def should_fail_run(status: RunOperationalStatus) -> bool:
    if not settings.INCIDENT_FAIL_RUN_ON_CRITICAL_GLOBAL_ALERT:
        return False
    if any(a.severity == "critical" for a in status.global_alerts):
        return True
    crit_stores = sum(1 for ss in status.store_statuses if any(a.severity == "critical" for a in ss.alerts))
    return crit_stores >= 2 and status.status == "failing"
