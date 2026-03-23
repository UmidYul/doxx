from __future__ import annotations

from unittest.mock import patch

from application.readiness.roadmap_planner import build_default_roadmap_from_gaps
from application.readiness.roadmap_report import (
    build_human_roadmap_report,
    build_roadmap_report,
    log_roadmap_events,
    summarize_phase_goals,
)
from application.readiness.readiness_report import build_production_readiness_report, build_human_readiness_report
from domain.production_readiness import ReadinessGap, ReadinessChecklistItem


def test_build_roadmap_report_shape() -> None:
    r = build_default_roadmap_from_gaps([], [])
    rep = build_roadmap_report(r)
    assert "critical_path" in rep
    assert "go_live_blockers" in rep
    assert "post_launch_item_codes" in rep
    assert "parallel_layers" in rep
    assert rep["item_count"] >= 1


def test_human_report_contains_sections() -> None:
    r = build_default_roadmap_from_gaps([], [])
    text = build_human_roadmap_report(r)
    assert "Critical path" in text
    assert "Canary go-live" in text
    assert "Go-live blockers" in text
    assert "Parallel workstreams" in text
    assert "defer post-launch" in text.lower() or "post-launch" in text.lower()


def test_summarize_phase_goals() -> None:
    r = build_default_roadmap_from_gaps([], [])
    g = summarize_phase_goals(r)
    assert "foundation" in g
    assert g["foundation"]


def test_log_roadmap_events_calls_logger() -> None:
    r = build_default_roadmap_from_gaps([], [])
    flat = [i for p in r.phases for i in p.items]
    with patch("application.readiness.roadmap_report.log_roadmap_event") as log_fn:
        log_roadmap_events(r, flat, r.dependencies)
        assert log_fn.call_count >= 1


def test_readiness_human_report_includes_roadmap_section() -> None:
    gap = ReadinessGap(
        domain="security",
        gap_code="sec.test",
        description="t",
        severity="critical",
        blocking=True,
        recommended_next_step="fix",
    )
    chk = ReadinessChecklistItem(
        domain="security",
        item_code="sec.x",
        title="t",
        description="d",
        required=True,
        status="blocked",
        risk_if_missing="critical",
    )
    rep = build_production_readiness_report([chk], [gap], [])
    text = build_human_readiness_report(rep)
    assert "Implementation roadmap" in text or "roadmap" in text.lower()
    assert rep.roadmap_summary is not None
    assert rep.roadmap_top_blocker_item_codes
