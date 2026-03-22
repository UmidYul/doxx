from __future__ import annotations

from application.readiness.prioritization import (
    explain_priority,
    rank_roadmap_items,
    split_go_live_vs_post_launch,
)
from domain.implementation_roadmap import RoadmapItem


def _item(
    code: str,
    *,
    blocking: bool,
    phase: str,
    priority: str,
    workstream: str = "crawl",
) -> RoadmapItem:
    return RoadmapItem(
        item_code=code,
        title=code,
        workstream=workstream,  # type: ignore[arg-type]
        phase=phase,  # type: ignore[arg-type]
        priority=priority,  # type: ignore[arg-type]
        blocking_for_go_live=blocking,
        recommended_owner_area="a",
    )


def test_rank_puts_blocking_first() -> None:
    a = _item("a", blocking=False, phase="go_live_baseline", priority="p0")
    b = _item("b", blocking=True, phase="scale_maturity", priority="p3")
    ranked = rank_roadmap_items([a, b])
    assert ranked[0].item_code == "b"


def test_explain_priority_mentions_blocker() -> None:
    it = _item("x", blocking=True, phase="foundation", priority="p0", workstream="security")
    lines = explain_priority(it)
    assert any("go-live" in line.lower() or "go live" in line.lower() for line in lines)


def test_split_go_live_vs_post_launch() -> None:
    go = _item("g", blocking=True, phase="foundation", priority="p0")
    post = _item("p", blocking=False, phase="post_launch_hardening", priority="p2")
    gl, pl = split_go_live_vs_post_launch([go, post])
    assert gl[0].item_code == "g"
    assert pl[0].item_code == "p"


def test_non_blocking_go_live_phase_stays_in_go_live_bucket() -> None:
    it = _item("obs", blocking=False, phase="go_live_baseline", priority="p1", workstream="observability")
    gl, pl = split_go_live_vs_post_launch([it])
    assert it in gl
    assert pl == []
