from __future__ import annotations

from config.settings import settings
from domain.go_live import RollbackTrigger


def get_default_rollback_triggers() -> list[RollbackTrigger]:
    return [
        RollbackTrigger(
            trigger_code="rb.critical_transport_apply",
            title="Critical global CRM transport or apply incident",
            severity="critical",
            condition_description="Sustained apply failures or transport outage affecting all stores",
            recommended_action="rollback",
        ),
        RollbackTrigger(
            trigger_code="rb.malformed_response_spike",
            title="Malformed CRM response rate spike",
            severity="high",
            condition_description="Malformed response rate above stabilization threshold",
            recommended_action="investigate",
        ),
        RollbackTrigger(
            trigger_code="rb.rejected_item_surge",
            title="Rejected item rate surge",
            severity="high",
            condition_description="CRM rejected item rate above threshold",
            recommended_action="degrade_store",
        ),
        RollbackTrigger(
            trigger_code="rb.unresolved_reconciliation_surge",
            title="Unresolved reconciliation backlog surge",
            severity="high",
            condition_description="Unresolved reconciliation rate above threshold",
            recommended_action="pause_store",
        ),
        RollbackTrigger(
            trigger_code="rb.block_page_spike_canary",
            title="Block page spike on canary stores",
            severity="critical",
            condition_description="Anti-bot block rate on canary-enabled stores exceeds threshold",
            recommended_action="degrade_store",
        ),
        RollbackTrigger(
            trigger_code="rb.security_validation_failure",
            title="Security validation failure after cutover",
            severity="critical",
            condition_description="Startup or runtime security checks fail post-deploy",
            recommended_action="rollback",
        ),
        RollbackTrigger(
            trigger_code="rb.contract_drift_live",
            title="Unexpected contract drift in live path",
            severity="critical",
            condition_description="Live CRM responses diverge from contract tests / schema expectations",
            recommended_action="rollback",
        ),
    ]


def _f(t: RollbackTrigger, note: str) -> RollbackTrigger:
    return t.model_copy(update={"notes": [note]})


def evaluate_rollback_triggers(
    status_summary: dict[str, object] | None,
    recent_alerts: list[dict[str, object]] | None,
) -> list[RollbackTrigger]:
    if not getattr(settings, "ENABLE_ROLLBACK_TRIGGER_EVALUATION", True):
        return []

    st = status_summary or {}
    alerts = recent_alerts or []

    def _fval(key: str, default: float = 0.0) -> float:
        v = st.get(key)
        if isinstance(v, (int, float)):
            return float(v)
        return default

    crit_alerts = sum(1 for a in alerts if str(a.get("severity", "")).lower() == "critical")
    high_alerts = sum(1 for a in alerts if str(a.get("severity", "")).lower() == "high")

    fired: list[RollbackTrigger] = []
    catalog = {t.trigger_code: t for t in get_default_rollback_triggers()}

    if st.get("critical_transport_apply_incident") is True or crit_alerts >= 3:
        fired.append(_f(catalog["rb.critical_transport_apply"], "critical_incident_or_alert_spike"))

    if _fval("malformed_response_rate", 0.0) > settings.STABILIZATION_MAX_MALFORMED_RESPONSE_RATE:
        fired.append(_f(catalog["rb.malformed_response_spike"], "malformed_rate_threshold"))

    if _fval("rejected_item_rate", 0.0) > settings.STABILIZATION_MAX_REJECTED_ITEM_RATE:
        fired.append(_f(catalog["rb.rejected_item_surge"], "rejected_rate_threshold"))

    if _fval("unresolved_reconciliation_rate", 0.0) > settings.STABILIZATION_MAX_UNRESOLVED_RECONCILIATION_RATE:
        fired.append(_f(catalog["rb.unresolved_reconciliation_surge"], "reconciliation_rate_threshold"))

    if _fval("block_page_rate", 0.0) > settings.STABILIZATION_MAX_BLOCK_PAGE_RATE and st.get("canary_store_scope") is True:
        fired.append(_f(catalog["rb.block_page_spike_canary"], "block_rate_on_canary"))

    if st.get("security_validation_failed_post_cutover") is True:
        fired.append(_f(catalog["rb.security_validation_failure"], "security_check_failed"))

    if st.get("live_contract_drift_detected") is True:
        fired.append(_f(catalog["rb.contract_drift_live"], "contract_drift_flag"))

    return fired
