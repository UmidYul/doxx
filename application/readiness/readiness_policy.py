from __future__ import annotations

from domain.production_readiness import (
    ReadinessChecklistItem,
    ReadinessGap,
    ReadinessRecommendedAction,
    ReadinessStatus,
)


def is_go_live_blocked(gaps: list[ReadinessGap]) -> bool:
    return any(g.blocking for g in gaps)


def compute_overall_readiness_status(
    checklist: list[ReadinessChecklistItem],
    gaps: list[ReadinessGap],
) -> ReadinessStatus:
    if is_go_live_blocked(gaps):
        return "blocked"
    required = [i for i in checklist if i.required]
    if required and all(i.status == "ready" for i in required):
        return "ready"
    if any(i.status in ("partial", "ready") for i in required):
        return "partial"
    return "not_started"


def recommend_readiness_action(
    status: ReadinessStatus,
    gaps: list[ReadinessGap],
) -> ReadinessRecommendedAction:
    if status == "blocked" or is_go_live_blocked(gaps):
        return "fix_blockers"
    if status == "ready":
        return "prepare_go_live"
    if status == "partial":
        return "continue_build"
    return "not_ready"
