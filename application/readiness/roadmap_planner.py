from __future__ import annotations

from domain.implementation_roadmap import (
    ImplementationRoadmap,
    PhasePlan,
    PriorityLevel,
    RoadmapItem,
    RoadmapPhase,
    Workstream,
)
from domain.production_readiness import ReadinessChecklistItem, ReadinessDomain, ReadinessGap

from application.readiness.phase_policy import get_phase_entry_criteria, get_phase_exit_criteria
from application.readiness.roadmap_dependencies import (
    build_roadmap_dependencies,
    detect_parallelizable_items,
    infer_critical_path,
)
from application.readiness.roadmap_report import log_roadmap_events


def _domain_to_workstream(domain: ReadinessDomain) -> Workstream:
    m: dict[ReadinessDomain, Workstream] = {
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
    return m[domain]


def _owner_area(domain: ReadinessDomain) -> str:
    return f"{domain}_owner"


def is_go_live_blocker(gap: ReadinessGap) -> bool:
    return bool(gap.blocking)


def assign_priority_for_gap(gap: ReadinessGap) -> PriorityLevel:
    if gap.blocking and gap.severity == "critical":
        return "p0"
    if gap.blocking or gap.severity == "critical":
        return "p1"
    if gap.severity == "high":
        return "p2"
    return "p3"


def assign_phase_for_gap(gap: ReadinessGap) -> RoadmapPhase:
    """Phase placement from domain + blocking + severity (10B)."""
    if gap.domain in ("security", "crm_integration") and (gap.blocking or gap.severity == "critical"):
        return "foundation"
    if gap.domain == "crawl" and gap.blocking:
        return "foundation"
    if gap.blocking:
        return "go_live_baseline"
    if gap.domain in ("performance",):
        return "post_launch_hardening"
    if gap.domain in ("documentation", "supportability") and gap.severity in ("low", "medium"):
        return "post_launch_hardening"
    if gap.severity == "low":
        return "scale_maturity"
    return "post_launch_hardening"


def infer_workstream_for_gap(gap: ReadinessGap) -> Workstream:
    return _domain_to_workstream(gap.domain)


def _effort_for_gap(gap: ReadinessGap) -> str:
    if gap.severity == "critical":
        return "large"
    if gap.severity == "high":
        return "medium"
    return "small"


def _item_from_gap(gap: ReadinessGap) -> RoadmapItem:
    phase = assign_phase_for_gap(gap)
    return RoadmapItem(
        item_code=f"gap:{gap.gap_code}",
        title=gap.description[:80] + ("…" if len(gap.description) > 80 else ""),
        workstream=infer_workstream_for_gap(gap),
        phase=phase,
        priority=assign_priority_for_gap(gap),
        depends_on=[],
        blocking_for_go_live=is_go_live_blocker(gap),
        recommended_owner_area=_owner_area(gap.domain),
        effort=_effort_for_gap(gap),  # type: ignore[arg-type]
        notes=[gap.recommended_next_step],
    )


def _item_from_checklist(chk: ReadinessChecklistItem) -> RoadmapItem | None:
    if chk.status == "ready" or not chk.required:
        return None
    gap_like_sev = chk.risk_if_missing
    gap = ReadinessGap(
        domain=chk.domain,
        gap_code=f"checklist.{chk.item_code}",
        description=f"{chk.title}: {chk.description[:100]}",
        severity=gap_like_sev,
        blocking=chk.risk_if_missing == "critical" or chk.domain in ("security", "crm_integration"),
        recommended_next_step=f"Bring {chk.item_code} to ready",
    )
    return _item_from_gap(gap)


def build_default_roadmap_from_gaps(
    gaps: list[ReadinessGap],
    checklist: list[ReadinessChecklistItem],
    *,
    emit_structured_logs: bool = False,
) -> ImplementationRoadmap:
    """Turn readiness gaps + non-ready checklist rows into a phased roadmap."""
    items: list[RoadmapItem] = []
    seen: set[str] = set()
    for g in gaps:
        it = _item_from_gap(g)
        if it.item_code not in seen:
            seen.add(it.item_code)
            items.append(it)
    for c in checklist:
        it = _item_from_checklist(c)
        if it and it.item_code not in seen:
            seen.add(it.item_code)
            items.append(it)

    if not items:
        items = _default_seed_items()

    dependencies = build_roadmap_dependencies(items)
    critical = infer_critical_path(items, dependencies)
    parallel = detect_parallelizable_items(items, dependencies)
    _ = parallel  # available for report

    by_phase: dict[RoadmapPhase, list[RoadmapItem]] = {p: [] for p in ("foundation", "go_live_baseline", "post_launch_hardening", "scale_maturity")}
    for it in items:
        by_phase[it.phase].append(it)

    phases: list[PhasePlan] = []
    for ph in ("foundation", "go_live_baseline", "post_launch_hardening", "scale_maturity"):
        pp: RoadmapPhase = ph  # type: ignore[assignment]
        phases.append(
            PhasePlan(
                phase=pp,
                goals=_goals_for_phase(pp),
                items=by_phase[pp],
                entry_criteria=get_phase_entry_criteria(pp),
                exit_criteria=get_phase_exit_criteria(pp),
            )
        )

    go_live_blockers = [i.item_code for i in items if i.blocking_for_go_live]
    post_launch = [
        i.item_code
        for i in items
        if not i.blocking_for_go_live and i.phase in ("post_launch_hardening", "scale_maturity")
    ]

    roadmap = ImplementationRoadmap(
        phases=phases,
        dependencies=dependencies,
        critical_path=critical,
        go_live_blockers=go_live_blockers,
        post_launch_items=post_launch,
    )

    if emit_structured_logs:
        log_roadmap_events(roadmap, items, dependencies)
    return roadmap


def _goals_for_phase(phase: RoadmapPhase) -> list[str]:
    if phase == "foundation":
        return [
            "Runnable crawl with safety guards",
            "CRM transport + auth to non-prod",
            "Security baseline enforced",
        ]
    if phase == "go_live_baseline":
        return [
            "Lifecycle + batch delivery correctness",
            "Observability + support minimum",
            "Release gates + rollout policy",
        ]
    if phase == "post_launch_hardening":
        return ["Replay/cost/perf hardening", "Operator feedback loop"]
    return ["Store expansion + advanced governance"]


def _default_seed_items() -> list[RoadmapItem]:
    """When no gaps: show canonical critical path skeleton (deferrable post-launch called out in docs)."""
    return [
        RoadmapItem(
            item_code="seed:foundation.security",
            title="Security baseline locked",
            workstream="security",
            phase="foundation",
            priority="p0",
            depends_on=[],
            blocking_for_go_live=True,
            recommended_owner_area="security_owner",
            effort="medium",
        ),
        RoadmapItem(
            item_code="seed:foundation.crm_transport",
            title="CRM HTTP transport verified",
            workstream="crm_integration",
            phase="foundation",
            priority="p0",
            depends_on=["seed:foundation.security"],
            blocking_for_go_live=True,
            recommended_owner_area="integrations_owner",
            effort="medium",
        ),
        RoadmapItem(
            item_code="seed:go_live.observability",
            title="Observability minimum for canary",
            workstream="observability",
            phase="go_live_baseline",
            priority="p1",
            depends_on=["seed:foundation.crm_transport"],
            blocking_for_go_live=True,
            recommended_owner_area="platform_owner",
            effort="medium",
        ),
        RoadmapItem(
            item_code="seed:post.cost_tuning",
            title="Cost/perf tuning after first traffic",
            workstream="performance",
            phase="post_launch_hardening",
            priority="p2",
            depends_on=["seed:go_live.observability"],
            blocking_for_go_live=False,
            recommended_owner_area="platform_owner",
            effort="small",
        ),
    ]
