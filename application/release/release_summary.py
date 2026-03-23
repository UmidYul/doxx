from __future__ import annotations

from config.settings import settings
from domain.release_quality import ReleaseReadinessSummary


def build_release_report(
    release_summary: ReleaseReadinessSummary,
    *,
    migration_readiness: dict[str, object] | None = None,
) -> dict[str, object]:
    failed_critical_checks = [c.check_name for c in release_summary.checks if not c.passed and c.category != "integration_like"]
    failed_contracts = [c.check_name for c in release_summary.checks if not c.passed and c.category == "contract"]
    stores_failed = [c.check_name.removeprefix("store_acceptance:") for c in release_summary.checks if not c.passed and c.category == "acceptance"]
    failed_gates = [g.gate_name for g in release_summary.gates if not g.passed]
    rep: dict[str, object] = {
        "overall_passed": release_summary.overall_passed,
        "recommended_action": release_summary.recommended_action,
        "critical_failures": release_summary.critical_failures,
        "warnings": release_summary.warnings,
        "failed_critical_checks": failed_critical_checks,
        "failed_contract_checks": failed_contracts,
        "stores_failing_acceptance": stores_failed,
        "failed_quality_gates": failed_gates,
        "checks_total": len(release_summary.checks),
        "gates_total": len(release_summary.gates),
    }
    if migration_readiness is not None and getattr(settings, "ENABLE_MIGRATION_READINESS_REPORT", True):
        rep["migration_readiness"] = migration_readiness
    if getattr(settings, "ENABLE_GO_LIVE_POLICY", True):
        rep["go_live_note"] = (
            "Release overall_passed is not automatic go-live approval; run parser go-live assessment (10C) before CRM cutover."
        )
    return rep


def build_human_release_report(release_summary: ReleaseReadinessSummary) -> str:
    rep = build_release_report(release_summary)
    lines = [
        f"Release readiness: overall_passed={rep['overall_passed']} action={rep['recommended_action']}",
        f"Critical failures (count): {rep['critical_failures']} | Warnings: {rep['warnings']}",
    ]
    if rep["failed_quality_gates"]:
        lines.append(f"Failed gates: {', '.join(rep['failed_quality_gates'])}")
    if rep["failed_contract_checks"]:
        lines.append(f"Contract drift: {', '.join(rep['failed_contract_checks'])}")
    if rep["stores_failing_acceptance"]:
        lines.append(f"Store acceptance failed: {', '.join(rep['stores_failing_acceptance'])}")
    if rep["failed_critical_checks"]:
        lines.append(f"Other failed checks: {', '.join(rep['failed_critical_checks'])}")
    if release_summary.recommended_action == "release":
        lines.append("Ship: no blocking gates recorded in this summary.")
    elif release_summary.recommended_action == "release_with_caution":
        lines.append("Ship with caution: resolve warnings before next release.")
    else:
        lines.append("Do not ship: fix critical failures first.")
    if getattr(settings, "ENABLE_GO_LIVE_POLICY", True):
        lines.append(
            "Go-live: even when release is green, cutover requires exit criteria + cutover checklist (see docs/go_live_policy.md)."
        )
    return "\n".join(lines)
