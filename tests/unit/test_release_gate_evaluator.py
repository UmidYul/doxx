from __future__ import annotations

from domain.release_quality import QualityGateResult, ReleaseCheckResult

from application.release.release_gate_evaluator import (
    build_release_readiness_summary,
    decide_release_action,
    evaluate_release_gates,
)


def test_evaluate_release_gates_all_pass():
    gates = evaluate_release_gates(
        {
            "critical_unit_tests_passed": True,
            "contract_tests_passed": True,
            "store_acceptance_passed": True,
            "payload_compatibility_passed": True,
            "lifecycle_replay_safety_passed": True,
            "malformed_response_regression_ok": True,
            "mapping_coverage_regression_ok": True,
            "parse_success_golden_ok": True,
            "compatibility_core_surfaces_clean": True,
            "compatibility_no_unplanned_breaking": True,
            "migration_readiness_acceptable": True,
            "deprecation_removal_safe": True,
            "dual_shape_plan_when_needed": True,
            "cost_perf_regression_gate_ok": True,
            "store_efficiency_policy_ok": True,
            "arch_dependency_gate_ok": True,
            "arch_anti_pattern_gate_ok": True,
            "architecture_lint_report_ok": True,
            "arch_core_import_gate_ok": True,
            "docs_required_present": True,
            "store_playbooks_for_enabled_stores": True,
            "crm_integration_release_support_docs_present": True,
            "docs_coverage_acceptable": True,
            "knowledge_continuity_no_critical_gaps": True,
            "readiness_no_critical_blocking_gaps": True,
            "readiness_required_domains_not_blocked": True,
            "readiness_report_available": True,
            "readiness_enabled_stores_have_evidence": True,
            "readiness_critical_evidence_security_crm_release": True,
        }
    )
    assert len(gates) == 29
    assert all(g.passed for g in gates)


def test_evaluate_release_gates_missing_key_fails():
    gates = evaluate_release_gates({})
    assert any(not g.passed for g in gates)


def test_mapping_coverage_regression_fails_gate():
    gates = evaluate_release_gates(
        {
            "critical_unit_tests_passed": True,
            "contract_tests_passed": True,
            "store_acceptance_passed": True,
            "payload_compatibility_passed": True,
            "lifecycle_replay_safety_passed": True,
            "malformed_response_regression_ok": True,
            "mapping_coverage_regression_ok": False,
            "parse_success_golden_ok": True,
            "compatibility_core_surfaces_clean": True,
            "compatibility_no_unplanned_breaking": True,
            "migration_readiness_acceptable": True,
            "deprecation_removal_safe": True,
            "dual_shape_plan_when_needed": True,
            "cost_perf_regression_gate_ok": True,
            "store_efficiency_policy_ok": True,
            "arch_dependency_gate_ok": True,
            "arch_anti_pattern_gate_ok": True,
            "architecture_lint_report_ok": True,
            "arch_core_import_gate_ok": True,
            "docs_required_present": True,
            "store_playbooks_for_enabled_stores": True,
            "crm_integration_release_support_docs_present": True,
            "docs_coverage_acceptable": True,
            "knowledge_continuity_no_critical_gaps": True,
            "readiness_no_critical_blocking_gaps": True,
            "readiness_required_domains_not_blocked": True,
            "readiness_report_available": True,
            "readiness_enabled_stores_have_evidence": True,
            "readiness_critical_evidence_security_crm_release": True,
        }
    )
    mc = next(g for g in gates if g.gate_name == "mapping_coverage_regression")
    assert mc.passed is False
    assert mc.severity == "high"


def test_release_summary_block_on_critical():
    gates = [
        QualityGateResult(gate_name="contract_tests", passed=False, severity="critical", details=["x"]),
    ]
    checks: list[ReleaseCheckResult] = []
    s = build_release_readiness_summary(checks, gates)
    assert s.critical_failures >= 1
    assert decide_release_action(s) == "block_release"
    assert s.recommended_action == "block_release"


def test_release_summary_caution_on_warnings_only():
    gates = [
        QualityGateResult(gate_name="g", passed=False, severity="warning", details=["w"]),
    ]
    checks: list[ReleaseCheckResult] = []
    s = build_release_readiness_summary(checks, gates)
    assert s.critical_failures == 0
    assert s.warnings >= 1
    assert s.recommended_action == "release_with_caution"
