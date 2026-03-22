from __future__ import annotations

from config.settings import settings
from domain.operational_policy import RunOperationalStatus, StoreOperationalStatus
from domain.operator_support import RunbookPlan, TriageSummary


def _clip(s: str, n: int = 500) -> str:
    if not getattr(settings, "ENABLE_DATA_MINIMIZATION", True):
        return s
    return s if len(s) <= n else s[:n] + "…"


def build_human_triage_message(summary: TriageSummary) -> str:
    store = summary.store_name or "run-wide"
    act = summary.recommended_action.replace("_", " ")
    cause = _clip(str(summary.suspected_root_cause or ""), 400)
    return (
        f"[{summary.run_id}] {store} | domain={summary.domain} | severity={summary.severity} | "
        f"likely_cause: {cause} | "
        f"recommended: {act} (confidence {summary.confidence}). "
        f"Evidence rows: {len(summary.evidence)} — inspect structured export, not raw logs."
    )


def build_human_runbook_message(plan: RunbookPlan) -> str:
    lines = [f"Runbook domain={plan.domain} severity={plan.severity} → final: {plan.final_recommendation}"]
    for s in plan.steps:
        lines.append(f"{s.step_order}. {_clip(s.title, 120)}: {_clip(s.instruction, 400)}")
    return " ".join(lines)


def dev_workflow_observability_hint() -> str:
    """Short pointer when DEV_MODE / structured DX events appear in logs (9B)."""
    return (
        "DEV_MODE / dx_event lines: see DEV_WORKFLOW.md for single-store runs, dry-run, "
        "fixture replay, and debug summaries."
    )


def build_human_status_message(status: RunOperationalStatus | StoreOperationalStatus) -> str:
    if isinstance(status, StoreOperationalStatus):
        na = len(status.alerts)
        bt = len(status.breached_thresholds)
        return (
            f"Store {status.status}: {status.store_name} | alerts={na} breached_thresholds={bt}. "
            f"Notes: {', '.join(status.notes) if status.notes else 'none'}."
        )
    crit = sum(1 for ss in status.store_statuses for a in ss.alerts if a.severity == "critical")
    crit += sum(1 for a in status.global_alerts if a.severity == "critical")
    degraded_stores = [ss.store_name for ss in status.store_statuses if ss.status != "healthy"]
    return (
        f"Run {status.status} (run_id={status.run_id}) | critical_alerts≈{crit} | "
        f"non_healthy_stores={len(degraded_stores)}. "
        f"Next: open operator_support.triage_run + diagnostic_run in ETL export."
    )
