from __future__ import annotations

from domain.implementation_roadmap import RoadmapItem

from application.readiness.phase_policy import phase_order_index


def _prio_rank(p: str) -> int:
    return {"p0": 0, "p1": 1, "p2": 2, "p3": 3}.get(p, 9)


def rank_roadmap_items(items: list[RoadmapItem]) -> list[RoadmapItem]:
    """Stable sort: go-live blockers and P0 first, then phase order."""
    return sorted(
        items,
        key=lambda i: (
            0 if i.blocking_for_go_live else 1,
            _prio_rank(i.priority),
            phase_order_index(i.phase),
            i.workstream,
            i.item_code,
        ),
    )


def explain_priority(item: RoadmapItem) -> list[str]:
    """Human-readable rationale for ordering (10B)."""
    lines: list[str] = []
    if item.blocking_for_go_live:
        lines.append("Blocks go-live cutover until closed.")
    if item.priority == "p0":
        lines.append("P0: immediate risk to security, CRM contract, or data integrity.")
    elif item.priority == "p1":
        lines.append("P1: required for safe canary or first prod traffic.")
    elif item.priority == "p2":
        lines.append("P2: hardening; usually post-launch or parallel track.")
    else:
        lines.append("P3: scale/maturity backlog.")
    if item.workstream in ("security", "crm_integration"):
        lines.append("Security/CRM streams are sequenced before widening rollout.")
    if item.phase in ("post_launch_hardening", "scale_maturity"):
        lines.append("Explicitly after first go-live baseline.")
    return lines


def split_go_live_vs_post_launch(items: list[RoadmapItem]) -> tuple[list[RoadmapItem], list[RoadmapItem]]:
    go_live = [i for i in items if i.blocking_for_go_live or i.phase in ("foundation", "go_live_baseline")]
    post = [i for i in items if i not in go_live]
    return go_live, post
