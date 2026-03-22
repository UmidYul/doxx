from __future__ import annotations

import logging

from domain.implementation_roadmap import ImplementationRoadmap, RoadmapDependency, RoadmapItem

from application.readiness.prioritization import rank_roadmap_items, split_go_live_vs_post_launch
from application.readiness.roadmap_dependencies import detect_parallelizable_items
from config.settings import settings
from infrastructure.observability import message_codes as obs_mc
from infrastructure.observability.event_logger import log_roadmap_event

logger = logging.getLogger("moscraper.roadmap")


def log_roadmap_events(
    roadmap: ImplementationRoadmap,
    items: list[RoadmapItem],
    dependencies: list[RoadmapDependency],
) -> None:
    if not getattr(settings, "ENABLE_STRUCTURED_SYNC_LOGS", True):
        return
    for it in items[:100]:
        log_roadmap_event(
            obs_mc.ROADMAP_ITEM_PLANNED,
            item_code=it.item_code,
            phase=it.phase,
            priority=it.priority,
            workstream=it.workstream,
            blocking_for_go_live=it.blocking_for_go_live,
            details={"title": it.title},
        )
    for d in dependencies[:200]:
        log_roadmap_event(
            obs_mc.ROADMAP_DEPENDENCY_INFERRED,
            dependency_from=d.from_item_code,
            dependency_to=d.to_item_code,
            reason=d.reason,
        )
    log_roadmap_event(
        obs_mc.ROADMAP_CRITICAL_PATH_BUILT,
        details={"critical_path": list(roadmap.critical_path)},
    )
    log_roadmap_event(
        obs_mc.ROADMAP_REPORT_BUILT,
        details={
            "go_live_blockers": len(roadmap.go_live_blockers),
            "post_launch": len(roadmap.post_launch_items),
        },
    )


def build_roadmap_report(roadmap: ImplementationRoadmap) -> dict[str, object]:
    flat = [i for p in roadmap.phases for i in p.items]
    ranked = rank_roadmap_items(flat)
    go_live, post = split_go_live_vs_post_launch(flat)
    parallel = detect_parallelizable_items(flat, roadmap.dependencies)
    return {
        "phase_count": len(roadmap.phases),
        "item_count": len(flat),
        "go_live_item_count": len(go_live),
        "post_launch_item_count": len(post),
        "critical_path": list(roadmap.critical_path),
        "go_live_blockers": list(roadmap.go_live_blockers),
        "post_launch_item_codes": list(roadmap.post_launch_items),
        "dependency_count": len(roadmap.dependencies),
        "parallel_layers": parallel,
        "top_ranked_item_codes": [i.item_code for i in ranked[:15]],
    }


def summarize_phase_goals(roadmap: ImplementationRoadmap) -> dict[str, list[str]]:
    return {p.phase: list(p.goals) for p in roadmap.phases}


def build_human_roadmap_report(roadmap: ImplementationRoadmap) -> str:
    flat = [i for p in roadmap.phases for i in p.items]
    parallel = detect_parallelizable_items(flat, roadmap.dependencies)
    lines = [
        "=== Implementation roadmap (10B) ===",
        "",
        "Critical path (ordered):",
        "  " + (" -> ".join(roadmap.critical_path) if roadmap.critical_path else "(empty)"),
        "",
        f"Go-live blockers ({len(roadmap.go_live_blockers)}):",
    ]
    for c in roadmap.go_live_blockers[:20]:
        lines.append(f"  - {c}")
    if not roadmap.go_live_blockers:
        lines.append("  (none)")

    lines.extend(["", "Phase-by-phase:", ""])
    for p in roadmap.phases:
        lines.append(f"## {p.phase}")
        lines.append("  Goals:")
        for g in p.goals:
            lines.append(f"    - {g}")
        lines.append(f"  Items: {len(p.items)}")
        for it in p.items[:12]:
            lines.append(
                f"    - [{it.priority}] {it.item_code} ({it.workstream}) "
                f"blocking_go_live={it.blocking_for_go_live}"
            )
        if len(p.items) > 12:
            lines.append(f"    ... +{len(p.items) - 12} more")
        lines.append("")

    lines.extend(["Parallel workstreams (by dependency layer):", ""])
    for idx, layer in enumerate(parallel[:8]):
        lines.append(f"  Layer {idx + 1}: {', '.join(layer[:10])}" + (" ..." if len(layer) > 10 else ""))

    lines.extend(
        [
            "",
            "Safe to defer post-launch (non-blocking / later phases):",
        ]
    )
    for c in roadmap.post_launch_items[:25]:
        lines.append(f"  - {c}")
    if not roadmap.post_launch_items:
        lines.append("  (none — tighten scope or add maturity backlog items)")

    return "\n".join(lines)
