from __future__ import annotations

from config.settings import settings
from domain.rollout_policy import RollbackDecision, RolloutScope, RolloutStage

from application.release import rollout_logger as rlog


def _alert_sev(a: object) -> str:
    return str(getattr(a, "severity", "") or "").lower()


def _alert_domain(a: object) -> str:
    return str(getattr(a, "domain", "") or "").lower()


def _critical_alerts(alerts: list[object] | None) -> list[object]:
    if not alerts:
        return []
    return [a for a in alerts if _alert_sev(a) == "critical"]


def decide_feature_rollback(
    feature_name: str,
    store_status: object | None = None,
    alerts: list[object] | None = None,
) -> RollbackDecision:
    if not settings.ENABLE_AUTO_ROLLBACK_ADVICE:
        return RollbackDecision(
            should_rollback=False,
            target_scope="feature",
            target_name=feature_name,
            reason="rollback_advice_disabled",
            recommended_stage="canary",
        )
    crit = _critical_alerts(alerts)
    st = str(getattr(store_status, "status", "") or "").lower()
    domain_hints: dict[str, tuple[str, ...]] = {
        "lifecycle_delta_events": ("lifecycle", "normalization"),
        "typed_specs_mapping": ("normalization", "parsing"),
        "replay_reconciliation": ("reconciliation", "crm_apply", "transport"),
        "browser_escalation_policy": ("anti_bot", "crawl"),
        "crm_http_transport": ("transport", "crm_apply"),
    }
    hints = domain_hints.get(feature_name, ())
    hit = [a for a in crit if _alert_domain(a) in hints]
    if hit and st != "failing":
        d = RollbackDecision(
            should_rollback=True,
            target_scope="feature",
            target_name=feature_name,
            reason=f"critical_alerts_in_feature_domains:{len(hit)}",
            recommended_stage="canary",
        )
        rlog.log_rollback_advice_emitted(scope="feature", target=feature_name, reason=d.reason, recommended_stage=d.recommended_stage)
        return d
    return RollbackDecision(
        should_rollback=False,
        target_scope="feature",
        target_name=feature_name,
        reason="no_feature_scoped_critical_signal",
        recommended_stage="full",
    )


def decide_store_rollback(
    store_name: str,
    store_status: object | None = None,
    alerts: list[object] | None = None,
) -> RollbackDecision:
    if not settings.ENABLE_AUTO_ROLLBACK_ADVICE:
        return RollbackDecision(
            should_rollback=False,
            target_scope="store",
            target_name=store_name,
            reason="rollback_advice_disabled",
            recommended_stage="partial",
        )
    crit = _critical_alerts(alerts)
    st = str(getattr(store_status, "status", "") or "").lower()
    store_crit = [a for a in crit if str(getattr(a, "store_name", "") or "").strip().lower() == store_name.strip().lower()]
    transport_global = [a for a in crit if "transport" in _alert_domain(a) or "GLOBAL" in str(getattr(a, "alert_code", ""))]
    if len(transport_global) >= 2:
        d = RollbackDecision(
            should_rollback=True,
            target_scope="global",
            target_name=None,
            reason="multi_critical_transport_or_global_signals",
            recommended_stage="canary",
        )
        rlog.log_rollback_advice_emitted(scope="global", target=None, reason=d.reason, recommended_stage=d.recommended_stage)
        return d
    if store_crit or st == "failing":
        d = RollbackDecision(
            should_rollback=True,
            target_scope="store",
            target_name=store_name,
            reason="store_critical_alerts_or_failing_status",
            recommended_stage="partial",
        )
        rlog.log_rollback_advice_emitted(scope="store", target=store_name, reason=d.reason, recommended_stage=d.recommended_stage)
        return d
    return RollbackDecision(
        should_rollback=False,
        target_scope="store",
        target_name=store_name,
        reason="no_store_scoped_critical_signal",
        recommended_stage="full",
    )


def explain_rollback_decision(decision: RollbackDecision) -> list[str]:
    lines = [
        f"should_rollback={decision.should_rollback}",
        f"scope={decision.target_scope} target={decision.target_name!r}",
        f"reason={decision.reason}",
        f"recommended_stage={decision.recommended_stage}",
    ]
    return lines
