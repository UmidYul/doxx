from __future__ import annotations

import re
from pathlib import Path

from domain.codebase_governance import DependencyViolation

from application.governance.dependency_policy import classify_dependency_violation, infer_layer_from_module
from application.governance.anti_patterns import explain_anti_pattern, list_known_anti_patterns

_RE_FROM = re.compile(r"^\s*from\s+([\w.]+)\s+import\s+")
_RE_IMPORT = re.compile(r"^\s*import\s+([\w.]+)")


def _path_to_dotted_module(root: Path, file_path: Path) -> str:
    rel = file_path.relative_to(root)
    parts = list(rel.with_suffix("").parts)
    return ".".join(parts)


def _extract_imports(text: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        line = line.split("#")[0]
        m = _RE_FROM.match(line)
        if m:
            mod = m.group(1)
            if mod.startswith("."):
                continue
            out.append(mod)
            continue
        m2 = _RE_IMPORT.match(line)
        if m2:
            mod = m2.group(1)
            if mod.startswith("."):
                continue
            out.append(mod)
    return out


def scan_module_imports(project_root: str) -> list[tuple[str, str]]:
    """Return (source_module, imported_top_level) pairs; best-effort."""
    root = Path(project_root).resolve()
    pairs: list[tuple[str, str]] = []
    for py in sorted(root.rglob("*.py")):
        if ".venv" in py.parts or "node_modules" in py.parts:
            continue
        try:
            rel_parts = py.relative_to(root).parts
        except ValueError:
            continue
        if not rel_parts or rel_parts[0] not in (
            "config",
            "domain",
            "application",
            "infrastructure",
            "tests",
            "scripts",
        ):
            continue
        try:
            text = py.read_text(encoding="utf-8")
        except OSError:
            continue
        src_mod = _path_to_dotted_module(root, py)
        for imp in _extract_imports(text):
            top = imp.split(".")[0]
            pairs.append((src_mod, top))
    return pairs


def detect_dependency_violations(project_root: str) -> list[DependencyViolation]:
    violations: list[DependencyViolation] = []
    seen: set[tuple[str, str]] = set()
    root = Path(project_root).resolve()
    for py in sorted(root.rglob("*.py")):
        if ".venv" in py.parts:
            continue
        try:
            rel_parts = py.relative_to(root).parts
        except ValueError:
            continue
        if not rel_parts or rel_parts[0] not in (
            "config",
            "domain",
            "application",
            "infrastructure",
            "tests",
            "scripts",
        ):
            continue
        try:
            text = py.read_text(encoding="utf-8")
        except OSError:
            continue
        src_mod = _path_to_dotted_module(root, py)
        for line in text.splitlines():
            line = line.split("#")[0]
            m = _RE_FROM.match(line)
            if not m:
                m = _RE_IMPORT.match(line)
            if not m:
                continue
            full = m.group(1)
            if full.startswith("."):
                continue
            key = (src_mod, full)
            if key in seen:
                continue
            seen.add(key)
            viol = classify_dependency_violation(src_mod, full)
            if viol is not None:
                violations.append(viol)
    return violations


def detect_common_anti_patterns(project_root: str) -> list[dict[str, object]]:
    """Heuristic smells by path and import tokens (9A pragmatic lint)."""
    root = Path(project_root).resolve()
    hits: list[dict[str, object]] = []

    for py in sorted(root.rglob("*.py")):
        if ".venv" in py.parts:
            continue
        try:
            rel = py.relative_to(root)
        except ValueError:
            continue
        srel = str(rel).replace("\\", "/")
        try:
            text = py.read_text(encoding="utf-8")
        except OSError:
            continue

        if "infrastructure/spiders/" in srel or srel.startswith("infrastructure\\spiders\\"):
            if "infrastructure.transports" in text or "transports." in text:
                hits.append(
                    {
                        "anti_pattern": "spider_contains_transport_logic",
                        "path": srel,
                        "severity": "high",
                        "hint": explain_anti_pattern("spider_contains_transport_logic"),
                    }
                )
            if "normalize" in text and "application.normalization" in text:
                hits.append(
                    {
                        "anti_pattern": "spider_contains_business_normalization",
                        "path": srel,
                        "severity": "warning",
                        "hint": explain_anti_pattern("spider_contains_business_normalization"),
                    }
                )

        if "infrastructure/pipelines/" in srel or srel.startswith("infrastructure\\pipelines\\"):
            if re.search(r"\bmediapark\b|\buzum\b", text, re.I) and "parse" in text.lower():
                hits.append(
                    {
                        "anti_pattern": "pipeline_contains_store_specific_parsing",
                        "path": srel,
                        "severity": "warning",
                        "hint": explain_anti_pattern("pipeline_contains_store_specific_parsing"),
                    }
                )

        if "infrastructure/transports/" in srel or srel.startswith("infrastructure\\transports\\"):
            if "entity_key" in text and "catalog" in text.lower():
                hits.append(
                    {
                        "anti_pattern": "transport_contains_catalog_matching_logic",
                        "path": srel,
                        "severity": "warning",
                        "hint": explain_anti_pattern("transport_contains_catalog_matching_logic"),
                    }
                )

        if srel.startswith("config/") or srel.startswith("config\\"):
            if "CrawlerProcess" in text:
                hits.append(
                    {
                        "anti_pattern": "config_contains_runtime_decision_logic",
                        "path": srel,
                        "severity": "high",
                        "hint": explain_anti_pattern("config_contains_runtime_decision_logic"),
                    }
                )

    return hits


def build_architecture_lint_report(project_root: str) -> dict[str, object]:
    violations = detect_dependency_violations(project_root)
    anti = detect_common_anti_patterns(project_root)
    critical_v = sum(1 for v in violations if v.severity == "critical")
    critical_a = sum(1 for a in anti if a.get("severity") == "critical")
    acceptable = critical_v == 0 and critical_a == 0
    return {
        "kind": "architecture_lint_v1",
        "project_root": str(Path(project_root).resolve()),
        "dependency_violation_count": len(violations),
        "critical_dependency_violations": critical_v,
        "anti_pattern_hits": len(anti),
        "critical_anti_patterns": critical_a,
        "acceptable": acceptable,
        "violations": [v.model_dump(mode="json") for v in violations],
        "anti_patterns": anti,
        "known_anti_pattern_ids": list_known_anti_patterns(),
    }


def detect_core_surface_forbidden_imports(project_root: str) -> list[DependencyViolation]:
    """Stricter check for domain/ and config/ only."""
    out: list[DependencyViolation] = []
    for v in detect_dependency_violations(project_root):
        if v.source_module.startswith("domain.") or v.source_module.startswith("config."):
            out.append(v)
    return out


def compute_architecture_gate_flags(project_root: str) -> dict[str, bool]:
    """Boolean inputs for release_gate_evaluator (9A); call from CI after checkout."""
    r = build_architecture_lint_report(project_root)
    core = detect_core_surface_forbidden_imports(project_root)
    return {
        "arch_dependency_gate_ok": int(r.get("critical_dependency_violations") or 0) == 0,
        "arch_anti_pattern_gate_ok": int(r.get("critical_anti_patterns") or 0) == 0,
        "architecture_lint_report_ok": bool(r.get("acceptable")),
        "arch_core_import_gate_ok": len(core) == 0,
    }
