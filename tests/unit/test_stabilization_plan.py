from __future__ import annotations

from application.go_live.stabilization_plan import (
    build_stabilization_checkpoints,
    evaluate_stabilization,
    summarize_stabilization_state,
)
from domain.go_live import RollbackTrigger


def test_build_checkpoints_three_windows() -> None:
    cps = build_stabilization_checkpoints()
    windows = {c.time_window for c in cps}
    assert windows == {"0-4h", "4-24h", "24-72h"}


def test_stabilization_fails_on_high_rejected_rate() -> None:
    cps = build_stabilization_checkpoints()
    out = evaluate_stabilization(
        cps,
        {"rejected_item_rate": 0.5},
        [],
        None,
    )
    mid = next(c for c in out if c.time_window == "4-24h")
    assert mid.passed is False


def test_outcome_successful_when_all_pass() -> None:
    cps = build_stabilization_checkpoints()
    ev = evaluate_stabilization(cps, {}, [], None)
    lo = summarize_stabilization_state(ev, [])
    assert lo.outcome == "successful"


def test_outcome_rolled_back_on_critical_trigger() -> None:
    cps = build_stabilization_checkpoints()
    ev = evaluate_stabilization(cps, {}, [], None)
    trig = RollbackTrigger(
        trigger_code="rb.critical_transport_apply",
        title="t",
        severity="critical",
        condition_description="c",
        recommended_action="rollback",
    )
    lo = summarize_stabilization_state(ev, [trig])
    assert lo.outcome == "rolled_back"


def test_outcome_degraded_on_high_trigger() -> None:
    cps = build_stabilization_checkpoints()
    ev = evaluate_stabilization(cps, {}, [], None)
    trig = RollbackTrigger(
        trigger_code="rb.rejected_item_surge",
        title="t",
        severity="high",
        condition_description="c",
        recommended_action="degrade_store",
    )
    lo = summarize_stabilization_state(ev, [trig])
    assert lo.outcome == "degraded"
