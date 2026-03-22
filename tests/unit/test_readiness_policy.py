from __future__ import annotations

from domain.production_readiness import ReadinessChecklistItem, ReadinessGap

from application.readiness.readiness_policy import (
    compute_overall_readiness_status,
    is_go_live_blocked,
    recommend_readiness_action,
)


def _item(domain: str, code: str, status: str, req: bool = True) -> ReadinessChecklistItem:
    return ReadinessChecklistItem(
        domain=domain,  # type: ignore[arg-type]
        item_code=code,
        title="t",
        description="d",
        required=req,
        status=status,  # type: ignore[arg-type]
        risk_if_missing="high",
        evidence_required=["unit_tests"],
    )


def test_blocked_when_blocking_gap() -> None:
    gaps = [
        ReadinessGap(
            domain="security",
            gap_code="g",
            description="x",
            severity="critical",
            blocking=True,
            recommended_next_step="fix",
        )
    ]
    cl = [_item("security", "s", "partial")]
    assert is_go_live_blocked(gaps)
    assert compute_overall_readiness_status(cl, gaps) == "blocked"
    assert recommend_readiness_action("blocked", gaps) == "fix_blockers"


def test_ready_when_all_required_ready_no_gaps() -> None:
    cl = [_item("crawl", "c", "ready"), _item("security", "s", "ready")]
    assert compute_overall_readiness_status(cl, []) == "ready"
    assert recommend_readiness_action("ready", []) == "prepare_go_live"


def test_partial_overall() -> None:
    cl = [_item("crawl", "c", "partial"), _item("security", "s", "ready")]
    gaps = [
        ReadinessGap(
            domain="crawl",
            gap_code="g",
            description="x",
            severity="medium",
            blocking=False,
            recommended_next_step="n",
        )
    ]
    assert compute_overall_readiness_status(cl, gaps) == "partial"
    assert recommend_readiness_action("partial", gaps) == "continue_build"
