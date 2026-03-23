from __future__ import annotations

from application.go_live.exit_criteria_registry import (
    evaluate_exit_criteria,
    get_default_exit_criteria,
    get_required_exit_criteria,
)
from domain.production_readiness import ProductionReadinessReport
from domain.release_quality import ReleaseReadinessSummary


def _report(overall: str = "ready") -> ProductionReadinessReport:
    return ProductionReadinessReport(
        overall_status=overall,  # type: ignore[arg-type]
        domains=["crawl"],
        checklist=[],
        gaps=[],
        evidence=[],
        blocking_gaps_count=0,
        critical_risk_count=0,
        recommended_action="prepare_go_live",
    )


def test_default_exit_criteria_minimum_count() -> None:
    d = get_default_exit_criteria()
    assert len(d) >= 10
    assert all(c.required for c in get_required_exit_criteria())


def test_evaluate_readiness_blocked_fails() -> None:
    crit = evaluate_exit_criteria(_report("blocked"), None, {}, {})
    exit_read = next(c for c in crit if c.criterion_code == "exit.readiness_not_blocked")
    assert exit_read.passed is False


def test_evaluate_release_missing_fails_when_required() -> None:
    crit = evaluate_exit_criteria(_report("ready"), None, {}, {})
    rel = next(c for c in crit if c.criterion_code == "exit.release_gates_clean")
    assert rel.passed is False


def test_evaluate_release_passes_with_summary() -> None:
    rs = ReleaseReadinessSummary(
        overall_passed=True,
        critical_failures=0,
        checks=[],
        gates=[],
        recommended_action="release",
    )
    st = {
        "security_baseline_validated": True,
        "observability_baseline_ok": True,
        "rollout_policy_configured": True,
        "crm_contract_checks_pass": True,
        "lifecycle_compatibility_clean": True,
        "dry_run_passed": True,
        "smoke_passed": True,
        "contract_checks_passed": True,
        "canary_scope_confirmed": True,
    }
    doc = {"enabled_stores": ["x"], "missing_playbooks": []}
    crit = evaluate_exit_criteria(_report("ready"), rs, st, doc)
    codes = {c.criterion_code: c.passed for c in crit}
    assert codes["exit.release_gates_clean"] is True
