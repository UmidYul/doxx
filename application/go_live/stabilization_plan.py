from __future__ import annotations

from config.settings import settings
from domain.go_live import LaunchOutcome, RollbackTrigger, StabilizationCheckpoint

from application.go_live.rollback_triggers import evaluate_rollback_triggers


def build_stabilization_checkpoints() -> list[StabilizationCheckpoint]:
    if not getattr(settings, "ENABLE_STABILIZATION_CHECKPOINTS", True):
        return []
    return [
        StabilizationCheckpoint(
            checkpoint_name="stabilization_hot_window",
            time_window="0-4h",
            checks=[
                "Critical alerts within budget; transport/apply sanity stable",
                "Rollout scope unchanged without approval",
                "No simultaneous widen + failing health signals",
            ],
            passed=True,
        ),
        StabilizationCheckpoint(
            checkpoint_name="stabilization_first_day",
            time_window="4-24h",
            checks=[
                "Per-store rejection/retryable patterns reviewed",
                "Reconciliation queue healthy vs thresholds",
                "Support/triage path exercised if incidents occurred",
            ],
            passed=True,
        ),
        StabilizationCheckpoint(
            checkpoint_name="stabilization_three_day",
            time_window="24-72h",
            checks=[
                "Performance/cost signals stable vs baseline",
                "Support load acceptable; runbooks updated if needed",
                "No hidden contract drift vs acceptance fixtures",
            ],
            passed=True,
        ),
    ]


def _rate(st: dict[str, object], key: str, default: float = 0.0) -> float:
    v = st.get(key)
    return float(v) if isinstance(v, (int, float)) else default


def _alerts(alerts: list[dict[str, object]] | None) -> tuple[int, int]:
    alerts = alerts or []
    crit = sum(1 for a in alerts if str(a.get("severity", "")).lower() == "critical")
    high = sum(1 for a in alerts if str(a.get("severity", "")).lower() == "high")
    return crit, high


def evaluate_stabilization(
    checkpoints: list[StabilizationCheckpoint],
    status_summary: dict[str, object] | None,
    alerts: list[dict[str, object]] | None,
    metrics: dict[str, object] | None,
) -> list[StabilizationCheckpoint]:
    st = dict(status_summary or {})
    if metrics:
        st.update(metrics)
    crit_n, high_n = _alerts(alerts)
    st.setdefault("critical_alert_count", crit_n)
    st.setdefault("high_alert_count", high_n)

    out: list[StabilizationCheckpoint] = []
    for cp in checkpoints:
        notes: list[str] = []
        passed = True

        if cp.time_window == "0-4h":
            if settings.STABILIZATION_BLOCK_ON_CRITICAL_ALERTS and crit_n > settings.STABILIZATION_MAX_CRITICAL_ALERTS:
                passed = False
                notes.append("critical_alerts_above_budget")
            if high_n > settings.STABILIZATION_MAX_HIGH_ALERTS:
                passed = False
                notes.append("high_alerts_above_budget")
            if _rate(st, "apply_success_rate", 1.0) < 0.85:  # default healthy if absent
                passed = False
                notes.append("apply_success_rate_low")

        elif cp.time_window == "4-24h":
            if _rate(st, "rejected_item_rate", 0.0) > settings.STABILIZATION_MAX_REJECTED_ITEM_RATE:
                passed = False
                notes.append("rejected_item_rate_high")
            if _rate(st, "unresolved_reconciliation_rate", 0.0) > settings.STABILIZATION_MAX_UNRESOLVED_RECONCILIATION_RATE:
                passed = False
                notes.append("unresolved_reconciliation_high")

        elif cp.time_window == "24-72h":
            if _rate(st, "malformed_response_rate", 0.0) > settings.STABILIZATION_MAX_MALFORMED_RESPONSE_RATE:
                passed = False
                notes.append("malformed_response_persists")
            if st.get("contract_drift_suspected") is True:
                passed = False
                notes.append("contract_drift_suspected")

        out.append(cp.model_copy(update={"passed": passed, "notes": notes}))

    return out


def summarize_stabilization_state(
    checkpoints: list[StabilizationCheckpoint],
    fired_rollback_triggers: list[RollbackTrigger],
    *,
    status_summary: dict[str, object] | None = None,
    alerts: list[dict[str, object]] | None = None,
) -> LaunchOutcome:
    any_crit_rb = any(t.severity == "critical" for t in fired_rollback_triggers)
    if any_crit_rb and getattr(settings, "ENABLE_ROLLBACK_TRIGGER_EVALUATION", True):
        return LaunchOutcome(
            outcome="rolled_back",
            summary="Critical rollback trigger fired; treat launch as rolled back or under active rollback.",
            followup_actions=["Execute rollback advisory", "CRM comms", "Post-incident checkpoint review"],
        )

    if fired_rollback_triggers:
        return LaunchOutcome(
            outcome="degraded",
            summary="High-severity triggers fired; system in degraded mode or partial pause.",
            followup_actions=["Apply degrade_store/pause_store per trigger", "Tighten scope to canary"],
        )

    if not checkpoints:
        return LaunchOutcome(
            outcome="stabilizing",
            summary="Stabilization checkpoints not enabled or not evaluated.",
            followup_actions=["Run evaluate_stabilization after cutover"],
        )

    if all(c.passed for c in checkpoints):
        return LaunchOutcome(
            outcome="successful",
            summary="All stabilization checkpoints passed; ready to declare steady state pending business sign-off.",
            followup_actions=["Move launch_stage to steady_state", "Schedule scale-up backlog review"],
        )

    return LaunchOutcome(
        outcome="stabilizing",
        summary="One or more stabilization checkpoints failed; continue observation before widening rollout.",
        followup_actions=["Review metrics vs thresholds", "Hold rollout promotion", "Update runbooks"],
    )


def stabilization_with_rollbacks(
    status_summary: dict[str, object] | None,
    alerts: list[dict[str, object]] | None,
    metrics: dict[str, object] | None,
) -> tuple[list[StabilizationCheckpoint], LaunchOutcome, list[RollbackTrigger]]:
    cps = build_stabilization_checkpoints()
    evaluated = evaluate_stabilization(cps, status_summary, alerts, metrics)
    fired = evaluate_rollback_triggers(status_summary, alerts)
    outcome = summarize_stabilization_state(evaluated, fired, status_summary=status_summary, alerts=alerts)
    return evaluated, outcome, fired
