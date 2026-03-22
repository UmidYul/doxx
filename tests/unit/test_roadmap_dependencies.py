from __future__ import annotations

from application.readiness.roadmap_dependencies import (
    build_roadmap_dependencies,
    detect_parallelizable_items,
    infer_critical_path,
)
from application.readiness.roadmap_planner import build_default_roadmap_from_gaps
from domain.implementation_roadmap import RoadmapDependency, RoadmapItem


def test_critical_path_orders_prerequisites() -> None:
    items = [
        RoadmapItem(
            item_code="a_sec",
            title="sec",
            workstream="security",
            phase="foundation",
            priority="p0",
            blocking_for_go_live=True,
            recommended_owner_area="x",
        ),
        RoadmapItem(
            item_code="b_crm",
            title="crm",
            workstream="crm_integration",
            phase="foundation",
            priority="p0",
            blocking_for_go_live=True,
            recommended_owner_area="x",
        ),
    ]
    deps = build_roadmap_dependencies(items)
    cp = infer_critical_path(items, deps)
    assert cp.index("a_sec") < cp.index("b_crm")


def test_critical_path_stable_for_default_seed() -> None:
    r = build_default_roadmap_from_gaps([], [])
    flat = [i for p in r.phases for i in p.items]
    cp = infer_critical_path(flat, r.dependencies)
    assert cp[0] == "seed:foundation.security"
    assert cp[-1] == "seed:post.cost_tuning"


def test_parallel_layers_same_phase_no_edge() -> None:
    items = [
        RoadmapItem(
            item_code="u1",
            title="u1",
            workstream="normalization",
            phase="foundation",
            priority="p2",
            blocking_for_go_live=False,
            recommended_owner_area="x",
        ),
        RoadmapItem(
            item_code="u2",
            title="u2",
            workstream="normalization",
            phase="foundation",
            priority="p2",
            blocking_for_go_live=False,
            recommended_owner_area="x",
        ),
    ]
    deps = build_roadmap_dependencies(items)
    layers = detect_parallelizable_items(items, deps)
    layer0 = layers[0]
    assert "u1" in layer0 and "u2" in layer0


def test_parallel_detect_default_seed_first_layer_has_security_only() -> None:
    r = build_default_roadmap_from_gaps([], [])
    flat = [i for p in r.phases for i in p.items]
    layers = detect_parallelizable_items(flat, r.dependencies)
    assert layers[0] == ["seed:foundation.security"]


def test_infer_critical_path_empty() -> None:
    assert infer_critical_path([], []) == []


def test_cycle_fallback_path() -> None:
    items = [
        RoadmapItem(
            item_code="x",
            title="x",
            workstream="crawl",
            phase="foundation",
            priority="p1",
            blocking_for_go_live=True,
            recommended_owner_area="a",
        ),
        RoadmapItem(
            item_code="y",
            title="y",
            workstream="crawl",
            phase="foundation",
            priority="p1",
            blocking_for_go_live=True,
            recommended_owner_area="a",
        ),
    ]
    deps = [
        RoadmapDependency(from_item_code="x", to_item_code="y", reason="r"),
        RoadmapDependency(from_item_code="y", to_item_code="x", reason="r"),
    ]
    cp = infer_critical_path(items, deps)
    assert len(cp) == 2
    assert set(cp) == {"x", "y"}
