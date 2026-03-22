from __future__ import annotations

from collections import Counter

from domain.codebase_governance import DependencyViolation


def build_maintainability_report(
    violations: list[DependencyViolation],
    anti_patterns: list[dict[str, object]],
) -> dict[str, object]:
    by_rule = Counter(v.violated_rule for v in violations)
    by_sev = Counter(v.severity for v in violations)
    ap_ids = [str(a.get("anti_pattern", "")) for a in anti_patterns]
    ap_counts = Counter(x for x in ap_ids if x)
    risky = sorted({v.source_module.split(".")[0] for v in violations})
    return {
        "kind": "maintainability_v1",
        "dependency_violation_total": len(violations),
        "violations_by_rule": dict(by_rule.most_common(20)),
        "violations_by_severity": dict(by_sev),
        "anti_pattern_total": len(anti_patterns),
        "anti_patterns_by_id": dict(ap_counts.most_common(20)),
        "risky_top_level_modules": risky[:30],
    }


def summarize_maintainability_risk(
    violations: list[DependencyViolation],
    anti_patterns: list[dict[str, object]],
) -> str:
    crit_v = sum(1 for v in violations if v.severity == "critical")
    crit_a = sum(1 for a in anti_patterns if a.get("severity") == "critical")
    if crit_v == 0 and crit_a == 0:
        return "maintainability_risk=low (no critical architecture signals in this scan)"
    return (
        f"maintainability_risk=elevated critical_dep_violations={crit_v} "
        f"critical_anti_patterns={crit_a}"
    )


def recommend_refactor_priorities(
    violations: list[DependencyViolation],
    anti_patterns: list[dict[str, object]],
) -> list[str]:
    out: list[str] = []
    for v in violations:
        if v.severity == "critical":
            out.append(f"fix_cross_layer_import:{v.source_module}->{v.target_module}")
    for a in anti_patterns:
        if a.get("severity") == "critical":
            out.append(f"fix_anti_pattern:{a.get('anti_pattern')}:{a.get('path')}")
    if not out:
        out.append("review_warnings_in_architecture_lint_report")
    return out[:50]
