"""Architecture governance helpers (9A): boundaries, placement hints, pragmatic lint."""

from application.governance.dependency_policy import (
    classify_dependency_violation,
    get_default_boundary_rules,
    infer_layer_from_module,
    is_dependency_allowed,
)
from application.governance.code_placement import decide_code_placement, get_responsibility_areas
from application.governance.anti_patterns import (
    explain_anti_pattern,
    list_known_anti_patterns,
    suggest_refactor_for_anti_pattern,
)
from application.governance.architecture_lint import (
    build_architecture_lint_report,
    compute_architecture_gate_flags,
    detect_common_anti_patterns,
    detect_core_surface_forbidden_imports,
    detect_dependency_violations,
    scan_module_imports,
)
from application.governance.maintainability_report import (
    build_maintainability_report,
    recommend_refactor_priorities,
    summarize_maintainability_risk,
)

__all__ = [
    "build_architecture_lint_report",
    "compute_architecture_gate_flags",
    "build_maintainability_report",
    "classify_dependency_violation",
    "decide_code_placement",
    "detect_common_anti_patterns",
    "detect_core_surface_forbidden_imports",
    "detect_dependency_violations",
    "explain_anti_pattern",
    "get_default_boundary_rules",
    "get_responsibility_areas",
    "infer_layer_from_module",
    "is_dependency_allowed",
    "list_known_anti_patterns",
    "recommend_refactor_priorities",
    "scan_module_imports",
    "suggest_refactor_for_anti_pattern",
    "summarize_maintainability_risk",
]
