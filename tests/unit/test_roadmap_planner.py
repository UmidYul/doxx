from __future__ import annotations

from application.readiness.roadmap_planner import (
    assign_phase_for_gap,
    assign_priority_for_gap,
    build_default_roadmap_from_gaps,
    infer_workstream_for_gap,
    is_go_live_blocker,
)
from domain.production_readiness import ReadinessGap


def test_blocking_gap_is_go_live_blocker() -> None:
    g = ReadinessGap(
        domain="lifecycle",
        gap_code="life.delta",
        description="Unsafe delta",
        severity="high",
        blocking=True,
        recommended_next_step="fix",
    )
    assert is_go_live_blocker(g) is True
    assert assign_priority_for_gap(g) in ("p0", "p1")


def test_critical_blocking_security_goes_foundation_p0() -> None:
    g = ReadinessGap(
        domain="security",
        gap_code="sec.x",
        description="Missing guard",
        severity="critical",
        blocking=True,
        recommended_next_step="enable",
    )
    assert assign_phase_for_gap(g) == "foundation"
    assert assign_priority_for_gap(g) == "p0"
    assert infer_workstream_for_gap(g) == "security"


def test_non_blocking_performance_goes_post_or_scale() -> None:
    g = ReadinessGap(
        domain="performance",
        gap_code="perf.tune",
        description="Tune pools",
        severity="medium",
        blocking=False,
        recommended_next_step="measure",
    )
    assert assign_phase_for_gap(g) == "post_launch_hardening"
    assert infer_workstream_for_gap(g) == "performance"


def test_non_blocking_low_severity_can_scale_maturity() -> None:
    g = ReadinessGap(
        domain="normalization",
        gap_code="norm.extra",
        description="Nice to have",
        severity="low",
        blocking=False,
        recommended_next_step="write",
    )
    assert assign_phase_for_gap(g) == "scale_maturity"


def test_default_roadmap_seed_when_no_gaps() -> None:
    r = build_default_roadmap_from_gaps([], [])
    codes = {i.item_code for p in r.phases for i in p.items}
    assert "seed:foundation.security" in codes
    assert r.critical_path
    post = set(r.post_launch_items)
    assert "seed:post.cost_tuning" in post


def test_blocking_gap_roadmap_item_high_priority() -> None:
    g = ReadinessGap(
        domain="crm_integration",
        gap_code="crm.auth",
        description="Auth rotation",
        severity="high",
        blocking=True,
        recommended_next_step="rotate",
    )
    r = build_default_roadmap_from_gaps([g], [])
    item = next(i for p in r.phases for i in p.items if i.item_code == "gap:crm.auth")
    assert item.blocking_for_go_live is True
    assert item.phase in ("foundation", "go_live_baseline")
    assert item.priority in ("p0", "p1")
