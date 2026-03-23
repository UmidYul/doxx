from __future__ import annotations

from config.settings import settings
from domain.go_live import ExitCriterion, GoLiveAssessment, GoLiveDecision, LaunchStage
from domain.implementation_roadmap import ImplementationRoadmap
from domain.production_readiness import ProductionReadinessReport
from domain.release_quality import ReleaseReadinessSummary

from application.go_live.cutover_checklist import build_cutover_checklist, evaluate_cutover_checklist
from application.go_live.exit_criteria_registry import evaluate_exit_criteria


def _merge_status_with_rollout(
    status_summary: dict[str, object] | None,
    rollout_summary: dict[str, object] | None,
) -> dict[str, object]:
    out = dict(status_summary or {})
    if not rollout_summary or not getattr(settings, "GO_LIVE_CANARY_ONLY_FIRST", True):
        return out
    stores_by_stage = rollout_summary.get("stores_by_stage") or {}
    enabled = list(getattr(settings, "STORE_NAMES", []) or [])
    if not enabled:
        return out
    canary = set(stores_by_stage.get("canary") or [])
    bad = set(stores_by_stage.get("full") or []) | set(stores_by_stage.get("partial") or [])
    violation = any(s in bad for s in enabled)
    all_on_canary = all(s in canary for s in enabled)
    if "full_rollout_without_canary_violation" not in out:
        out["full_rollout_without_canary_violation"] = violation
    if "canary_scope_confirmed" not in out:
        out["canary_scope_confirmed"] = all_on_canary and not violation
    return out


def explain_no_go_reasons(
    exit_criteria: list[ExitCriterion],
    cutover_blocking: list[str],
    extra: list[str] | None = None,
) -> list[str]:
    reasons: list[str] = []
    for c in exit_criteria:
        if c.required and not c.passed:
            reasons.append(f"{c.criterion_code}: {c.title}")
    for code in cutover_blocking:
        reasons.append(f"cutover.{code}")
    reasons.extend(extra or [])
    return reasons


def explain_go_with_constraints(
    exit_criteria: list[ExitCriterion],
    constraints: list[str],
) -> list[str]:
    lines = list(constraints)
    for c in exit_criteria:
        if not c.required:
            continue
        if not c.passed:
            continue
        if c.notes:
            lines.extend(c.notes)
    return lines


def decide_go_live(
    exit_criteria: list[ExitCriterion],
    cutover_ok: bool,
    cutover_blocking: list[str],
    readiness_report: ProductionReadinessReport,
) -> GoLiveDecision:
    failed_required = [c for c in exit_criteria if c.required and not c.passed]
    if failed_required or not cutover_ok or cutover_blocking:
        return "no_go"
    if readiness_report.overall_status == "partial":
        return "go_with_constraints"
    return "go"


def assess_go_live(
    readiness_report: ProductionReadinessReport,
    release_summary: ReleaseReadinessSummary | None,
    rollout_summary: dict[str, object] | None,
    status_summary: dict[str, object] | None,
    *,
    roadmap: ImplementationRoadmap | None = None,
    docs_coverage: dict[str, object] | None = None,
    launch_stage: LaunchStage = "pre_cutover",
    emit_structured_logs: bool = False,
) -> GoLiveAssessment:
    if not getattr(settings, "ENABLE_GO_LIVE_POLICY", True):
        return GoLiveAssessment(
            decision="no_go",
            launch_stage=launch_stage,
            exit_criteria=[],
            cutover_checklist=[],
            blocking_reasons=["ENABLE_GO_LIVE_POLICY is False"],
            constraints=[],
            recommended_action="Re-enable go-live policy in settings before cutover decision.",
        )

    merged = _merge_status_with_rollout(status_summary, rollout_summary)
    exit_criteria = evaluate_exit_criteria(readiness_report, release_summary, merged, docs_coverage)
    cutover = build_cutover_checklist(readiness_report, roadmap, rollout_summary, statuses=merged)
    cutover_ok, cutover_blocking = evaluate_cutover_checklist(cutover)

    decision = decide_go_live(exit_criteria, cutover_ok, cutover_blocking, readiness_report)

    blocking_reasons = explain_no_go_reasons(exit_criteria, cutover_blocking) if decision == "no_go" else []
    constraints: list[str] = []
    if decision == "go_with_constraints" and readiness_report.overall_status == "partial":
        constraints.append("readiness_overall_partial_document_waiver")

    if decision == "go":
        recommended = "Proceed with cutover during agreed window; run stabilization checkpoints."
    elif decision == "go_with_constraints":
        recommended = "Proceed only with documented waivers; keep scope on canary; expand after stabilization."
    else:
        recommended = "Do not cut over: close exit criteria and cutover blockers first."

    assessment = GoLiveAssessment(
        decision=decision,
        launch_stage=launch_stage,
        exit_criteria=exit_criteria,
        cutover_checklist=cutover,
        blocking_reasons=blocking_reasons,
        constraints=constraints,
        recommended_action=recommended,
    )

    if emit_structured_logs:
        from application.go_live.launch_report import log_cutover_evaluated, log_go_live_assessment_events

        log_cutover_evaluated(cutover_ok)
        log_go_live_assessment_events(assessment)

    return assessment
