from __future__ import annotations

from application.go_live.launch_report import build_go_live_report, build_human_go_live_report
from domain.go_live import GoLiveAssessment, LaunchOutcome


def test_build_go_live_report_shape() -> None:
    a = GoLiveAssessment(
        decision="go",
        launch_stage="pre_cutover",
        exit_criteria=[],
        cutover_checklist=[],
        blocking_reasons=[],
        constraints=[],
        recommended_action="Proceed",
    )
    o = LaunchOutcome(outcome="successful", summary="ok", followup_actions=[])
    d = build_go_live_report(a, o)
    assert d["decision"] == "go"
    assert d["outcome"] == "successful"


def test_human_report_contains_decision_and_blockers() -> None:
    a = GoLiveAssessment(
        decision="no_go",
        launch_stage="pre_cutover",
        exit_criteria=[],
        cutover_checklist=[],
        blocking_reasons=["exit.foo failed"],
        constraints=[],
        recommended_action="Stop",
    )
    o = LaunchOutcome(outcome="stabilizing", summary="waiting", followup_actions=[])
    text = build_human_go_live_report(a, o)
    assert "no_go" in text
    assert "exit.foo" in text
