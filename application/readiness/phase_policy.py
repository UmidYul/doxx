from __future__ import annotations

from domain.implementation_roadmap import RoadmapPhase
from domain.production_readiness import ProductionReadinessReport, ReadinessStatus


def get_phase_entry_criteria(phase: str) -> list[str]:
    """Formal entry gates per roadmap phase (10B)."""
    p = phase  # RoadmapPhase string
    if p == "foundation":
        return [
            "Team agrees on STORE_NAMES scope for first integration.",
            "CRM HTTP contract and credentials path agreed (non-prod first).",
        ]
    if p == "go_live_baseline":
        return [
            "Foundation exit criteria met (crawl + CRM transport + security baseline + smoke tests).",
            "No open P0 gaps in security or CRM integration.",
        ]
    if p == "post_launch_hardening":
        return [
            "First production or production-like traffic completed without blocking incidents.",
            "Rollback path validated once.",
        ]
    if p == "scale_maturity":
        return [
            "Post-launch hardening exit met (replay/cost/operator tooling baseline).",
            "Capacity plan for additional stores or volume agreed.",
        ]
    return []


def get_phase_exit_criteria(phase: str) -> list[str]:
    p = phase
    if p == "foundation":
        return [
            "Crawl framework runs for target store(s) with pagination/duplicate guards configured.",
            "CRM HTTP transport + parser auth path exercised in non-prod.",
            "Security baseline: redaction + outbound guards + startup validation enabled.",
            "Unit tests green for transport + security + normalize entrypoints.",
        ]
    if p == "go_live_baseline":
        return [
            "No readiness blocking gaps; overall status ready or agreed waiver documented.",
            "Lifecycle safe default + batch/retry semantics verified against CRM.",
            "Observability: structured logs + failure classification + minimum operator docs.",
            "Release/rollout policy and gates enforced in CI.",
            "Store playbooks + onboarding path exist for enabled stores.",
        ]
    if p == "post_launch_hardening":
        return [
            "Replay/reconciliation scenarios exercised with CRM in controlled replays.",
            "Cost/perf signals reviewed; regressions gated.",
            "Support runbooks updated from real incidents (if any).",
        ]
    if p == "scale_maturity":
        return [
            "Multi-store rollout pattern repeatable; resource budgets tuned.",
            "Advanced compatibility / deprecation policy exercised as needed.",
        ]
    return []


def _domain_worst_status(report: ProductionReadinessReport) -> dict[str, ReadinessStatus]:
    order = {"blocked": 4, "partial": 3, "ready": 2, "not_started": 1}
    worst: dict[str, int] = {}
    for item in report.checklist:
        worst[item.domain] = max(worst.get(item.domain, 0), order.get(item.status, 0))
    inv = {v: k for k, v in order.items()}
    return {d: inv.get(worst[d], "not_started") for d in worst}


def can_enter_phase(
    phase: str,
    readiness_report: ProductionReadinessReport,
    *,
    emit_structured_logs: bool = False,
) -> bool:
    """Pragmatic gate: use readiness rollup + blockers."""
    dom = _domain_worst_status(readiness_report)
    if phase == "foundation":
        ok = True
    elif phase == "go_live_baseline":
        ok_crawl = dom.get("crawl", "not_started") in ("ready", "partial")
        ok_crm = dom.get("crm_integration", "not_started") in ("ready", "partial")
        ok_sec = dom.get("security", "not_started") in ("ready", "partial")
        ok = bool(ok_crawl and ok_crm and ok_sec and readiness_report.blocking_gaps_count == 0)
    elif phase == "post_launch_hardening":
        ok = readiness_report.overall_status in ("ready", "partial") and readiness_report.blocking_gaps_count == 0
    elif phase == "scale_maturity":
        ok = readiness_report.overall_status == "ready" and readiness_report.blocking_gaps_count == 0
    else:
        ok = False

    if emit_structured_logs and not ok:
        from infrastructure.observability import message_codes as obs_mc
        from infrastructure.observability.event_logger import log_roadmap_event

        log_roadmap_event(
            obs_mc.PHASE_ENTRY_BLOCKED,
            phase=phase,
            details={
                "overall_status": readiness_report.overall_status,
                "blocking_gaps_count": readiness_report.blocking_gaps_count,
            },
        )
    return ok


def can_exit_phase(
    phase: str,
    readiness_report: ProductionReadinessReport,
    *,
    emit_structured_logs: bool = False,
) -> bool:
    dom = _domain_worst_status(readiness_report)
    if phase == "foundation":
        need = ("crawl", "crm_integration", "security")
        ok = all(dom.get(d) == "ready" for d in need) and readiness_report.blocking_gaps_count == 0
    elif phase == "go_live_baseline":
        need = (
            "lifecycle",
            "batch_apply",
            "replay_reconciliation",
            "observability",
            "release_governance",
            "documentation",
        )
        ok = readiness_report.overall_status == "ready" and all(dom.get(d) == "ready" for d in need)
    elif phase == "post_launch_hardening":
        perf_ok = dom.get("performance", "ready") in ("ready", "partial")
        sup_ok = dom.get("supportability", "ready") in ("ready", "partial")
        ok = readiness_report.overall_status == "ready" and perf_ok and sup_ok
    elif phase == "scale_maturity":
        ok = readiness_report.overall_status == "ready" and readiness_report.critical_risk_count == 0
    else:
        ok = False

    if emit_structured_logs and ok:
        from infrastructure.observability import message_codes as obs_mc
        from infrastructure.observability.event_logger import log_roadmap_event

        log_roadmap_event(obs_mc.PHASE_EXIT_APPROVED, phase=phase)
    return ok


def phase_order_index(phase: RoadmapPhase) -> int:
    return {"foundation": 0, "go_live_baseline": 1, "post_launch_hardening": 2, "scale_maturity": 3}[phase]
