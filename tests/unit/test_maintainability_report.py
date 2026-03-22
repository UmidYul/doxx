from __future__ import annotations

from domain.codebase_governance import DependencyViolation
from application.governance.maintainability_report import (
    build_maintainability_report,
    recommend_refactor_priorities,
    summarize_maintainability_risk,
)


def test_report_summarizes_violations() -> None:
    v = [
        DependencyViolation(
            source_module="domain.x",
            target_module="infrastructure.y",
            violated_rule="domain must not depend on infrastructure",
            severity="critical",
            reason="r",
        )
    ]
    r = build_maintainability_report(v, [])
    assert r["dependency_violation_total"] == 1
    assert "violations_by_rule" in r


def test_summarize_risk_elevated_when_critical() -> None:
    v = [
        DependencyViolation(
            source_module="domain.x",
            target_module="infrastructure.y",
            violated_rule="x",
            severity="critical",
            reason="r",
        )
    ]
    s = summarize_maintainability_risk(v, [])
    assert "elevated" in s


def test_recommend_priorities() -> None:
    v = [
        DependencyViolation(
            source_module="domain.x",
            target_module="app.y",
            violated_rule="x",
            severity="critical",
            reason="r",
        )
    ]
    out = recommend_refactor_priorities(v, [])
    assert any("fix_cross_layer" in x for x in out)
