from __future__ import annotations

from pathlib import Path

from domain.production_readiness import (
    ProductionReadinessReport,
    ReadinessChecklistItem,
    ReadinessDomain,
    ReadinessEvidence,
    ReadinessGap,
)
from domain.release_quality import ReleaseReadinessSummary

from application.readiness.gap_assessor import infer_blocking_gaps
from application.readiness.readiness_policy import (
    compute_overall_readiness_status,
    is_go_live_blocked,
    recommend_readiness_action,
)

_WORKSTREAM_FOR_DOMAIN: dict[ReadinessDomain, str] = {
    "crawl": "crawl",
    "normalization": "normalization",
    "crm_integration": "crm_integration",
    "lifecycle": "lifecycle",
    "batch_apply": "crm_integration",
    "replay_reconciliation": "lifecycle",
    "observability": "observability",
    "supportability": "support",
    "security": "security",
    "performance": "performance",
    "release_governance": "release_governance",
    "documentation": "documentation",
}


def enrich_readiness_with_roadmap(report: ProductionReadinessReport) -> ProductionReadinessReport:
    """Attach phased roadmap summary, critical path, and domain hints (10B)."""
    from application.readiness.prioritization import rank_roadmap_items
    from application.readiness.roadmap_planner import (
        assign_phase_for_gap,
        build_default_roadmap_from_gaps,
        infer_workstream_for_gap,
    )
    from application.readiness.roadmap_report import build_roadmap_report

    roadmap = build_default_roadmap_from_gaps(report.gaps, report.checklist)
    summary = build_roadmap_report(roadmap)
    dom_roll = summarize_domain_statuses(report)
    hints: dict[str, str] = {}
    for d in report.domains:
        if dom_roll.get(d) != "blocked":
            continue
        gaps_d = [g for g in report.gaps if g.domain == d]
        if gaps_d:
            sev_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
            pick = max(gaps_d, key=lambda g: (g.blocking, sev_order.get(g.severity, 0)))
            ph = assign_phase_for_gap(pick)
            ws = infer_workstream_for_gap(pick)
            hints[d] = f"{ph}/{ws}"
        else:
            hints[d] = f"go_live_baseline/{_WORKSTREAM_FOR_DOMAIN.get(d, 'unknown')}"

    flat = [i for p in roadmap.phases for i in p.items]
    ranked = rank_roadmap_items(flat)
    top_blockers = [i.item_code for i in ranked if i.blocking_for_go_live][:15]

    return report.model_copy(
        update={
            "roadmap_summary": summary,
            "roadmap_critical_path": list(roadmap.critical_path),
            "roadmap_phase_hints_by_domain": hints,
            "roadmap_top_blocker_item_codes": top_blockers,
        }
    )


def enrich_readiness_with_go_live(
    report: ProductionReadinessReport,
    *,
    release_summary: ReleaseReadinessSummary | None = None,
    rollout_summary: dict[str, object] | None = None,
    status_summary: dict[str, object] | None = None,
    docs_coverage: dict[str, object] | None = None,
    roadmap: object | None = None,
) -> ProductionReadinessReport:
    """Attach go-live assessment snapshot (10C) using exit criteria + cutover checklist."""
    from config.settings import settings

    if not getattr(settings, "ENABLE_GO_LIVE_POLICY", True):
        return report
    from application.go_live.go_live_policy import assess_go_live
    from application.readiness.roadmap_planner import build_default_roadmap_from_gaps

    rm = roadmap
    if rm is None:
        rm = build_default_roadmap_from_gaps(report.gaps, report.checklist)
    assessment = assess_go_live(
        report,
        release_summary,
        rollout_summary,
        status_summary,
        roadmap=rm,
        docs_coverage=docs_coverage,
    )
    failed = [c.criterion_code for c in assessment.exit_criteria if c.required and not c.passed]
    cut_block = [i.item_code for i in assessment.cutover_checklist if i.blocking and not i.completed]
    summary: dict[str, object] = {
        "decision": assessment.decision,
        "launch_stage": assessment.launch_stage,
        "recommended_action": assessment.recommended_action,
        "blocking_reasons": list(assessment.blocking_reasons),
        "constraints": list(assessment.constraints),
    }
    return report.model_copy(
        update={
            "go_live_assessment_summary": summary,
            "go_live_failed_exit_criteria": failed,
            "go_live_blocking_cutover_items": cut_block,
        }
    )


def build_production_readiness_report(
    checklist: list[ReadinessChecklistItem],
    gaps: list[ReadinessGap],
    evidence: list[ReadinessEvidence],
    *,
    release_summary: ReleaseReadinessSummary | None = None,
    rollout_summary: dict[str, object] | None = None,
    status_summary: dict[str, object] | None = None,
    docs_coverage: dict[str, object] | None = None,
) -> ProductionReadinessReport:
    """Single aggregate readiness view for parser → CRM (10A–10C)."""
    domains = sorted({i.domain for i in checklist}, key=lambda d: d)
    blocking = infer_blocking_gaps(gaps)
    critical_risk_count = sum(1 for g in gaps if g.severity == "critical")
    overall = compute_overall_readiness_status(checklist, gaps)
    action = recommend_readiness_action(overall, gaps)
    base = ProductionReadinessReport(
        overall_status=overall,
        domains=list(domains),
        checklist=list(checklist),
        gaps=list(gaps),
        evidence=list(evidence),
        blocking_gaps_count=len(blocking),
        critical_risk_count=critical_risk_count,
        recommended_action=action,
    )
    r = enrich_readiness_with_roadmap(base)
    return enrich_readiness_with_go_live(
        r,
        release_summary=release_summary,
        rollout_summary=rollout_summary,
        status_summary=status_summary,
        docs_coverage=docs_coverage,
    )


def summarize_domain_statuses(report: ProductionReadinessReport) -> dict[str, str]:
    """Worst status per domain (blocked > partial > ready > not_started)."""
    order = {"blocked": 4, "partial": 3, "ready": 2, "not_started": 1}
    worst: dict[str, int] = {}
    for item in report.checklist:
        cur = worst.get(item.domain, 0)
        worst[item.domain] = max(cur, order.get(item.status, 0))
    inv = {v: k for k, v in order.items()}
    return {d: inv.get(worst[d], "unknown") for d in sorted(worst.keys())}


def build_human_readiness_report(report: ProductionReadinessReport) -> str:
    lines = [
        f"Overall: {report.overall_status}",
        f"Recommended action: {report.recommended_action}",
        f"Blocking gaps: {report.blocking_gaps_count} | Critical-risk gaps: {report.critical_risk_count}",
        "",
        "Blocking / critical gaps (top):",
    ]
    top_gaps = [g for g in report.gaps if g.blocking or g.severity == "critical"][:12]
    if not top_gaps:
        lines.append("  (none)")
    for g in top_gaps:
        lines.append(f"  - [{g.domain}] {g.gap_code} ({g.severity}, blocking={g.blocking}): {g.description[:100]}")

    dom = summarize_domain_statuses(report)
    lines.extend(["", "Domain rollup:"])
    for d, s in sorted(dom.items()):
        lines.append(f"  - {d}: {s}")

    ready_d = [d for d, s in dom.items() if s == "ready"]
    partial_d = [d for d, s in dom.items() if s == "partial"]
    lines.extend(
        [
            "",
            f"Domains ready: {', '.join(ready_d) or '-'}",
            f"Domains partial: {', '.join(partial_d) or '-'}",
            "",
            "Next actions:",
        ]
    )
    if report.recommended_action == "fix_blockers":
        lines.append("  Resolve blocking gaps in security, CRM integration, idempotency, batch semantics, or store playbooks.")
    elif report.recommended_action == "prepare_go_live":
        lines.append("  Run final release gates, confirm CRM cutover window, enable rollout stage per policy.")
    elif report.recommended_action == "continue_build":
        lines.append("  Close partial items; add evidence (tests/docs/metrics) where status is partial.")
    else:
        lines.append("  Establish baseline checklist items and minimum evidence before reassessing.")

    if report.roadmap_summary:
        lines.extend(
            [
                "",
                "Implementation roadmap (10B):",
                f"  Planned items: {report.roadmap_summary.get('item_count', 0)} "
                f"(go-live scope: {report.roadmap_summary.get('go_live_item_count', 0)}, "
                f"deferrable: {report.roadmap_summary.get('post_launch_item_count', 0)})",
            ]
        )
    if report.roadmap_critical_path:
        cp = report.roadmap_critical_path[:10]
        lines.append(f"  Critical path (codes): {' -> '.join(cp)}" + (" …" if len(report.roadmap_critical_path) > 10 else ""))
    if report.roadmap_top_blocker_item_codes:
        tb = report.roadmap_top_blocker_item_codes[:10]
        lines.append(f"  Top roadmap blocker items: {', '.join(tb)}")
    if report.roadmap_phase_hints_by_domain:
        lines.append("  Blocked domains → suggested phase/workstream:")
        for d, h in sorted(report.roadmap_phase_hints_by_domain.items())[:12]:
            lines.append(f"    - {d}: {h}")

    from config.settings import settings as _settings

    if getattr(_settings, "ENABLE_GO_LIVE_POLICY", True):
        lines.extend(
            [
                "",
                "Go-live policy (10C): a green readiness rollup or passing CI release checks alone does not authorize CRM cutover.",
                "  Run assess_go_live with release + rollout snapshots, exit criteria, dry-run/smoke signals, and cutover checklist.",
            ]
        )
    if report.go_live_assessment_summary:
        gl = report.go_live_assessment_summary
        lines.extend(
            [
                "",
                "Go-live assessment snapshot:",
                f"  Decision: {gl.get('decision')} | Stage: {gl.get('launch_stage')}",
                f"  Action: {gl.get('recommended_action')}",
            ]
        )
        if report.go_live_failed_exit_criteria:
            lines.append("  Failed exit criteria: " + ", ".join(report.go_live_failed_exit_criteria[:10]))
        if report.go_live_blocking_cutover_items:
            lines.append("  Open blocking cutover items: " + ", ".join(report.go_live_blocking_cutover_items[:10]))

    return "\n".join(lines)


def compute_readiness_gate_flags(
    project_root: str,
    *,
    store_names: list[str] | None = None,
    emit_structured_logs: bool = False,
) -> dict[str, bool]:
    """Boolean inputs for :func:`application.release.release_gate_evaluator.evaluate_release_gates` (10A)."""
    from application.readiness.evidence_collector import collect_readiness_evidence
    from application.readiness.gap_assessor import assess_readiness_gaps, update_checklist_status_from_evidence
    from application.readiness.readiness_registry import get_default_readiness_checklist
    from config.settings import settings as app_settings
    from infrastructure.observability import message_codes as obs_mc
    from infrastructure.observability.event_logger import log_readiness_event

    root = Path(project_root)
    stores = [s.strip() for s in (store_names or list(app_settings.STORE_NAMES)) if s.strip()]
    evidence = collect_readiness_evidence(project_root)
    checklist = update_checklist_status_from_evidence(
        get_default_readiness_checklist(),
        evidence,
        project_root,
        store_names=stores,
    )
    gaps = assess_readiness_gaps(checklist, evidence)
    report = build_production_readiness_report(checklist, gaps, evidence)

    if emit_structured_logs:
        log_readiness_event(
            obs_mc.READINESS_EVIDENCE_COLLECTED,
            domain="*",
            evidence_type="config",
            artifact_name="readiness_evidence_bundle",
            details={"count": len(evidence)},
        )
        for g in gaps[:50]:
            log_readiness_event(
                obs_mc.READINESS_GAP_DETECTED,
                domain=g.domain,
                gap_code=g.gap_code,
                severity=g.severity,
                blocking=g.blocking,
            )
        log_readiness_event(
            obs_mc.READINESS_STATUS_COMPUTED,
            overall_status=report.overall_status,
            details={"blocking_gaps": report.blocking_gaps_count},
        )
        log_readiness_event(
            obs_mc.READINESS_REPORT_BUILT,
            overall_status=report.overall_status,
            details={"recommended_action": report.recommended_action},
        )
        if report.blocking_gaps_count:
            log_readiness_event(
                obs_mc.READINESS_BLOCKER_FOUND,
                overall_status=report.overall_status,
                details={"blocking_gaps_count": report.blocking_gaps_count},
            )

    critical_codes = {
        "sec.redaction",
        "sec.outbound_guards",
        "crm.transport",
        "crm.auth",
        "crm.payload_contract",
        "rel.contract_gates",
    }
    by_code = {i.item_code: i.status for i in checklist}
    critical_subset_ready = all(by_code.get(c) == "ready" for c in critical_codes)

    domain_blocked: set[ReadinessDomain] = set()
    for item in checklist:
        if item.required and item.status == "blocked":
            domain_blocked.add(item.domain)

    required_domains_ok = len(domain_blocked) == 0 and not is_go_live_blocked(gaps)

    store_playbooks_ok = all((root / "docs" / "stores" / f"{s.lower()}.md").is_file() for s in stores)

    return {
        "readiness_no_critical_blocking_gaps": not any(g.blocking for g in gaps),
        "readiness_required_domains_not_blocked": required_domains_ok,
        "readiness_report_available": True,
        "readiness_enabled_stores_have_evidence": store_playbooks_ok,
        "readiness_critical_evidence_security_crm_release": critical_subset_ready,
    }
