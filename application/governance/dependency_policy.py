from __future__ import annotations

from domain.codebase_governance import DependencyViolation, ModuleBoundaryRule

# First path segment after repo root maps to a logical layer for imports like `domain.foo`.
_LAYER_PREFIXES: tuple[tuple[str, str], ...] = (
    ("config", "config"),
    ("domain", "domain"),
    ("application", "application"),
    ("infrastructure", "infrastructure"),
    ("tests", "tests"),
    ("scripts", "scripts"),
)


def get_default_boundary_rules() -> list[ModuleBoundaryRule]:
    """Formalized dependency policy (9A). Not exhaustive; complements code review."""
    return [
        ModuleBoundaryRule(
            layer="domain",
            allowed_dependencies=["domain"],
            forbidden_dependencies=["application", "infrastructure", "tests", "scripts"],
            notes=["Pure models/contracts; no I/O or framework imports."],
        ),
        ModuleBoundaryRule(
            layer="config",
            allowed_dependencies=["config", "domain", "infrastructure"],
            forbidden_dependencies=["application", "tests", "scripts"],
            notes=[
                "Pydantic Settings and Scrapy glue; may import small infrastructure helpers "
                "(e.g. proxy policy for download handlers). Avoid business orchestration here.",
            ],
        ),
        ModuleBoundaryRule(
            layer="application",
            allowed_dependencies=["config", "domain", "application", "infrastructure"],
            forbidden_dependencies=["tests", "scripts"],
            notes=[
                "Use-cases and policies; may import infrastructure for thin adapters (logging, "
                "metrics). Keep business rules here; heavy IO stays in infrastructure.",
            ],
        ),
        ModuleBoundaryRule(
            layer="infrastructure",
            allowed_dependencies=["config", "domain", "application", "infrastructure"],
            forbidden_dependencies=["tests", "scripts"],
            notes=["Adapters: spiders, transports, pipelines, IO."],
        ),
        ModuleBoundaryRule(
            layer="tests",
            allowed_dependencies=["config", "domain", "application", "infrastructure", "tests"],
            forbidden_dependencies=["scripts"],
            notes=["May import production packages for verification."],
        ),
        ModuleBoundaryRule(
            layer="scripts",
            allowed_dependencies=["config", "domain", "application", "infrastructure", "scripts"],
            forbidden_dependencies=["tests"],
            notes=["CLI and one-off tooling; not imported by runtime spiders."],
        ),
    ]


def infer_layer_from_module(module_path: str) -> str | None:
    """Map dotted module or path string to a top-level layer name."""
    s = (module_path or "").strip().replace("\\", "/")
    if not s:
        return None
    if "/" in s:
        parts = [p for p in s.split("/") if p]
        for prefix, layer in _LAYER_PREFIXES:
            if parts and parts[0] == prefix:
                return layer
        return None
    root = s.split(".")[0]
    for prefix, layer in _LAYER_PREFIXES:
        if root == prefix:
            return layer
    return None


def is_dependency_allowed(source_layer: str, target_layer: str) -> bool:
    rules = {r.layer: r for r in get_default_boundary_rules()}
    src = rules.get(source_layer)
    if src is None:
        return True
    if target_layer in src.forbidden_dependencies:
        return False
    if not src.allowed_dependencies:
        return True
    return target_layer in src.allowed_dependencies


def classify_dependency_violation(source_module: str, target_module: str) -> DependencyViolation | None:
    """Return a violation if import from source_module to target_module crosses policy."""
    sl = infer_layer_from_module(source_module)
    tl = infer_layer_from_module(target_module)
    if sl is None or tl is None:
        return None
    if sl == tl:
        return None
    if is_dependency_allowed(sl, tl):
        return None
    rule = f"{sl} must not depend on {tl}"
    severity = "high"
    if sl == "domain" and tl in ("infrastructure", "application"):
        severity = "critical"
    elif sl == "config" and tl == "infrastructure":
        severity = "high"
    elif sl in ("application", "infrastructure") and tl in ("tests", "scripts"):
        severity = "critical"
    return DependencyViolation(
        source_module=source_module,
        target_module=target_module,
        violated_rule=rule,
        severity=severity,
        reason=f"Policy: {rule} (see get_default_boundary_rules / PROJECT.md).",
    )
