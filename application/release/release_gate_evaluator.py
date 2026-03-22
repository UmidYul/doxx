from __future__ import annotations

from typing import Any

from domain.release_quality import (
    QualityGateResult,
    ReleaseAction,
    ReleaseCheckResult,
    GateSeverity,
    ReleaseReadinessSummary,
)

from application.release import compatibility_logger as compat_log
from application.release import release_logger as rel_log


def evaluate_release_gates(test_results: dict[str, object]) -> list[QualityGateResult]:
    """Map aggregated pytest / tooling results into quality gates (6A).

    Expected keys (all optional; missing → failed gate):
    - critical_unit_tests_passed: bool
    - contract_tests_passed: bool
    - store_acceptance_passed: bool
    - payload_compatibility_passed: bool
    - lifecycle_replay_safety_passed: bool
    - malformed_response_regression_ok: bool
    - mapping_coverage_regression_ok: bool
    - parse_success_golden_ok: bool
    - compatibility_core_surfaces_clean: bool
    - compatibility_no_unplanned_breaking: bool
    - migration_readiness_acceptable: bool
    - deprecation_removal_safe: bool
    - dual_shape_plan_when_needed: bool
    - cost_perf_regression_gate_ok: bool (8C — perf/cost vs baseline)
    - store_efficiency_policy_ok: bool (8C — efficiency / overhead policy)
    - arch_dependency_gate_ok: bool (9A — no critical dependency violations)
    - arch_anti_pattern_gate_ok: bool (9A — no critical anti-pattern hits)
    - architecture_lint_report_ok: bool (9A — lint report acceptable)
    - arch_core_import_gate_ok: bool (9A — domain/config surfaces clean)
    - docs_required_present: bool (9C — required docs on disk)
    - store_playbooks_for_enabled_stores: bool (9C — playbook per STORE_NAMES)
    - crm_integration_release_support_docs_present: bool (9C — CRM/support/release guides)
    - docs_coverage_acceptable: bool (9C — coverage threshold)
    - knowledge_continuity_no_critical_gaps: bool (9C — no critical doc/store gaps)
    - readiness_no_critical_blocking_gaps: bool (10A — no blocking readiness gaps)
    - readiness_required_domains_not_blocked: bool (10A — required domains not blocked)
    - readiness_report_available: bool (10A — assessment can be produced)
    - readiness_enabled_stores_have_evidence: bool (10A — store playbooks for enabled stores)
    - readiness_critical_evidence_security_crm_release: bool (10A — security/CRM/release evidence ready)
    """
    specs: list[tuple[str, str, GateSeverity]] = [
        ("critical_unit_tests", "critical_unit_tests_passed", "critical"),
        ("contract_tests", "contract_tests_passed", "critical"),
        ("store_acceptance", "store_acceptance_passed", "critical"),
        ("payload_compatibility", "payload_compatibility_passed", "critical"),
        ("lifecycle_replay_safety", "lifecycle_replay_safety_passed", "critical"),
        ("malformed_batch_regression", "malformed_response_regression_ok", "critical"),
        ("mapping_coverage_regression", "mapping_coverage_regression_ok", "high"),
        ("parse_success_golden", "parse_success_golden_ok", "high"),
        # --- Contract evolution (6C) ---
        ("compatibility_core_surfaces", "compatibility_core_surfaces_clean", "critical"),
        ("compatibility_no_unplanned_breaking", "compatibility_no_unplanned_breaking", "critical"),
        ("migration_readiness", "migration_readiness_acceptable", "critical"),
        ("deprecation_removal_policy", "deprecation_removal_safe", "high"),
        ("dual_shape_plan", "dual_shape_plan_when_needed", "high"),
        ("cost_perf_regression", "cost_perf_regression_gate_ok", "critical"),
        ("store_efficiency_policy", "store_efficiency_policy_ok", "high"),
        ("arch_dependency", "arch_dependency_gate_ok", "critical"),
        ("arch_anti_pattern", "arch_anti_pattern_gate_ok", "critical"),
        ("architecture_lint_report", "architecture_lint_report_ok", "high"),
        ("arch_core_imports", "arch_core_import_gate_ok", "critical"),
        ("docs_required", "docs_required_present", "critical"),
        ("store_playbooks", "store_playbooks_for_enabled_stores", "critical"),
        ("docs_support_crm_bundle", "crm_integration_release_support_docs_present", "critical"),
        ("docs_coverage", "docs_coverage_acceptable", "high"),
        ("knowledge_continuity", "knowledge_continuity_no_critical_gaps", "critical"),
        ("readiness_no_blocking_gaps", "readiness_no_critical_blocking_gaps", "critical"),
        ("readiness_domains_ok", "readiness_required_domains_not_blocked", "critical"),
        ("readiness_report", "readiness_report_available", "high"),
        ("readiness_store_evidence", "readiness_enabled_stores_have_evidence", "high"),
        ("readiness_critical_surface", "readiness_critical_evidence_security_crm_release", "critical"),
    ]
    gates: list[QualityGateResult] = []
    for gate_name, key, sev in specs:
        raw = test_results.get(key)
        passed = bool(raw) if raw is not None else False
        detail = "ok" if passed else f"flag {key!r} is missing or false"
        eff: GateSeverity = "info" if passed else sev
        gates.append(
            QualityGateResult(
                gate_name=gate_name,
                passed=passed,
                severity=eff,
                details=[detail],
                metrics={key: passed},
            )
        )
        rel_log.emit_release_gate_evaluated(
            gate_name=gate_name,
            passed=passed,
            severity=eff,
            details=[detail],
        )
        if not passed and gate_name in (
            "compatibility_core_surfaces",
            "compatibility_no_unplanned_breaking",
            "migration_readiness",
            "deprecation_removal_policy",
            "dual_shape_plan",
        ):
            compat_log.emit_compatibility_guard_blocked(
                surface="*",
                change_name=gate_name,
                recommended_action="resolve_contract_evolution_gate",
            )
    return gates


def decide_release_action(summary: ReleaseReadinessSummary) -> ReleaseAction:
    if summary.critical_failures > 0:
        return "block_release"
    if summary.warnings > 0:
        return "release_with_caution"
    return "release"


def build_release_readiness_summary(
    checks: list[ReleaseCheckResult],
    gates: list[QualityGateResult],
) -> ReleaseReadinessSummary:
    critical_failures = 0
    warnings = 0
    for g in gates:
        if g.passed:
            continue
        if g.severity in ("critical", "high"):
            critical_failures += 1
        elif g.severity in ("warning",):
            warnings += 1
    for c in checks:
        if c.passed:
            continue
        if c.category in ("unit", "contract", "acceptance", "compatibility", "regression"):
            critical_failures += 1
        elif c.category == "integration_like":
            warnings += 1
        else:
            warnings += 1

    tmp = ReleaseReadinessSummary(
        overall_passed=critical_failures == 0,
        critical_failures=critical_failures,
        warnings=warnings,
        checks=list(checks),
        gates=list(gates),
        recommended_action="release",
    )
    action = decide_release_action(tmp)
    out = tmp.model_copy(update={"recommended_action": action})
    if out.overall_passed and action == "release":
        rel_log.emit_release_ready()
    elif action == "block_release":
        rel_log.emit_release_blocked(reason="critical_failures", critical_failures=critical_failures)
    return out


def summarize_pytest_flags(
    *,
    unit_ok: bool,
    contract_ok: bool,
    acceptance_ok: bool,
    regression_ok: bool,
    payload_ok: bool = True,
    malformed_ok: bool = True,
    mapping_ok: bool = True,
    golden_parse_ok: bool = True,
    compatibility_core_ok: bool = True,
    compatibility_no_unplanned_breaking: bool = True,
    migration_readiness_ok: bool = True,
    deprecation_removal_safe: bool = True,
    dual_shape_plan_ok: bool = True,
    cost_perf_regression_ok: bool = True,
    store_efficiency_ok: bool = True,
    arch_dependency_ok: bool = True,
    arch_anti_pattern_ok: bool = True,
    architecture_lint_ok: bool = True,
    arch_core_import_ok: bool = True,
    docs_required_ok: bool = True,
    store_playbooks_ok: bool = True,
    crm_support_release_docs_ok: bool = True,
    docs_coverage_ok: bool = True,
    knowledge_continuity_ok: bool = True,
    readiness_no_blocking_ok: bool = True,
    readiness_domains_ok: bool = True,
    readiness_report_ok: bool = True,
    readiness_store_evidence_ok: bool = True,
    readiness_critical_surface_ok: bool = True,
) -> ReleaseReadinessSummary:
    """Convenience for local/CI scripts: fold booleans into gates + summary."""
    results: dict[str, Any] = {
        "critical_unit_tests_passed": unit_ok,
        "contract_tests_passed": contract_ok,
        "store_acceptance_passed": acceptance_ok,
        "payload_compatibility_passed": payload_ok,
        "lifecycle_replay_safety_passed": regression_ok,
        "malformed_response_regression_ok": malformed_ok,
        "mapping_coverage_regression_ok": mapping_ok,
        "parse_success_golden_ok": golden_parse_ok,
        "compatibility_core_surfaces_clean": compatibility_core_ok,
        "compatibility_no_unplanned_breaking": compatibility_no_unplanned_breaking,
        "migration_readiness_acceptable": migration_readiness_ok,
        "deprecation_removal_safe": deprecation_removal_safe,
        "dual_shape_plan_when_needed": dual_shape_plan_ok,
        "cost_perf_regression_gate_ok": cost_perf_regression_ok,
        "store_efficiency_policy_ok": store_efficiency_ok,
        "arch_dependency_gate_ok": arch_dependency_ok,
        "arch_anti_pattern_gate_ok": arch_anti_pattern_ok,
        "architecture_lint_report_ok": architecture_lint_ok,
        "arch_core_import_gate_ok": arch_core_import_ok,
        "docs_required_present": docs_required_ok,
        "store_playbooks_for_enabled_stores": store_playbooks_ok,
        "crm_integration_release_support_docs_present": crm_support_release_docs_ok,
        "docs_coverage_acceptable": docs_coverage_ok,
        "knowledge_continuity_no_critical_gaps": knowledge_continuity_ok,
        "readiness_no_critical_blocking_gaps": readiness_no_blocking_ok,
        "readiness_required_domains_not_blocked": readiness_domains_ok,
        "readiness_report_available": readiness_report_ok,
        "readiness_enabled_stores_have_evidence": readiness_store_evidence_ok,
        "readiness_critical_evidence_security_crm_release": readiness_critical_surface_ok,
    }
    gates = evaluate_release_gates(results)
    checks: list[ReleaseCheckResult] = []
    return build_release_readiness_summary(checks, gates)
