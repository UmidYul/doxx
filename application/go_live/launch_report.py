from __future__ import annotations

from config.settings import settings
from domain.go_live import GoLiveAssessment, LaunchOutcome, RollbackTrigger, StabilizationCheckpoint

from infrastructure.observability import message_codes as obs_mc
from infrastructure.observability.event_logger import log_go_live_event


def log_go_live_assessment_events(assessment: GoLiveAssessment) -> None:
    if not getattr(settings, "ENABLE_STRUCTURED_SYNC_LOGS", True):
        return
    log_go_live_event(
        obs_mc.GO_LIVE_ASSESSMENT_BUILT,
        decision=assessment.decision,
        launch_stage=assessment.launch_stage,
        recommended_action=assessment.recommended_action,
        details={"blocking_reasons": len(assessment.blocking_reasons), "constraints": len(assessment.constraints)},
    )
    log_go_live_event(
        obs_mc.GO_LIVE_DECISION_MADE,
        decision=assessment.decision,
        launch_stage=assessment.launch_stage,
        recommended_action=assessment.recommended_action,
    )
    for c in assessment.exit_criteria:
        if c.required and not c.passed:
            log_go_live_event(
                obs_mc.GO_LIVE_BLOCKER_DETECTED,
                criterion_code=c.criterion_code,
                passed=False,
                recommended_action=assessment.recommended_action,
                details={"title": c.title},
            )
    for item in assessment.cutover_checklist:
        if item.blocking and not item.completed:
            log_go_live_event(
                obs_mc.GO_LIVE_BLOCKER_DETECTED,
                item_code=item.item_code,
                passed=False,
                recommended_action=assessment.recommended_action,
            )


def log_cutover_evaluated(all_passed: bool) -> None:
    if not getattr(settings, "ENABLE_STRUCTURED_SYNC_LOGS", True):
        return
    log_go_live_event(
        obs_mc.CUTOVER_CHECKLIST_EVALUATED,
        passed=all_passed,
    )


def log_rollback_fired(t: RollbackTrigger) -> None:
    if not getattr(settings, "ENABLE_STRUCTURED_SYNC_LOGS", True):
        return
    log_go_live_event(
        obs_mc.ROLLBACK_TRIGGER_FIRED,
        trigger_code=t.trigger_code,
        severity=t.severity,
        recommended_action=t.recommended_action,
        details={"notes": t.notes},
    )


def log_stabilization_checkpoint(cp: StabilizationCheckpoint) -> None:
    if not getattr(settings, "ENABLE_STRUCTURED_SYNC_LOGS", True):
        return
    log_go_live_event(
        obs_mc.STABILIZATION_CHECKPOINT_EVALUATED,
        passed=cp.passed,
        details={"checkpoint": cp.checkpoint_name, "window": cp.time_window, "notes": cp.notes},
    )


def log_launch_outcome(outcome: LaunchOutcome) -> None:
    if not getattr(settings, "ENABLE_STRUCTURED_SYNC_LOGS", True):
        return
    log_go_live_event(
        obs_mc.LAUNCH_OUTCOME_SUMMARIZED,
        details={
            "outcome": outcome.outcome,
            "summary": outcome.summary,
            "followups": outcome.followup_actions,
        },
    )


def build_go_live_report(
    assessment: GoLiveAssessment,
    outcome: LaunchOutcome,
    *,
    fired_triggers: list[RollbackTrigger] | None = None,
    stabilization: list[StabilizationCheckpoint] | None = None,
) -> dict[str, object]:
    return {
        "decision": assessment.decision,
        "launch_stage": assessment.launch_stage,
        "recommended_action": assessment.recommended_action,
        "blocking_reasons": list(assessment.blocking_reasons),
        "constraints": list(assessment.constraints),
        "exit_criteria_failed": [c.criterion_code for c in assessment.exit_criteria if c.required and not c.passed],
        "cutover_blocking_open": [i.item_code for i in assessment.cutover_checklist if i.blocking and not i.completed],
        "outcome": outcome.outcome,
        "outcome_summary": outcome.summary,
        "followup_actions": list(outcome.followup_actions),
        "rollback_triggers_fired": [t.trigger_code for t in (fired_triggers or [])],
        "stabilization_checkpoints": [
            {"name": c.checkpoint_name, "window": c.time_window, "passed": c.passed} for c in (stabilization or [])
        ],
    }


def build_human_go_live_report(
    assessment: GoLiveAssessment,
    outcome: LaunchOutcome,
    *,
    fired_triggers: list[RollbackTrigger] | None = None,
    stabilization: list[StabilizationCheckpoint] | None = None,
) -> str:
    lines = [
        "=== Go-live assessment (10C) ===",
        f"Decision: {assessment.decision} | Stage: {assessment.launch_stage}",
        f"Recommended action: {assessment.recommended_action}",
        "",
        "Blocking reasons (if no-go):",
    ]
    for b in assessment.blocking_reasons[:20]:
        lines.append(f"  - {b}")
    if not assessment.blocking_reasons:
        lines.append("  (none)")
    lines.extend(["", "Constraints / waivers:"])
    for c in assessment.constraints[:20]:
        lines.append(f"  - {c}")
    if not assessment.constraints:
        lines.append("  (none)")
    lines.extend(
        [
            "",
            f"Stabilization outcome: {outcome.outcome}",
            f"  {outcome.summary}",
            "",
            "Rollback triggers fired:",
        ]
    )
    ft = fired_triggers or []
    if not ft:
        lines.append("  (none)")
    for t in ft:
        lines.append(f"  - [{t.severity}] {t.trigger_code}: {t.recommended_action}")
    lines.extend(["", "Stabilization checkpoints:"])
    st = stabilization or []
    if not st:
        lines.append("  (none)")
    for c in st:
        lines.append(f"  - {c.checkpoint_name} ({c.time_window}): passed={c.passed}")
    lines.extend(["", "Next steps (outcome follow-ups):"])
    for f in outcome.followup_actions[:12]:
        lines.append(f"  - {f}")
    if not outcome.followup_actions:
        lines.append("  (none)")
    return "\n".join(lines)
