from __future__ import annotations

import tempfile
from pathlib import Path

from application.governance.architecture_lint import (
    build_architecture_lint_report,
    compute_architecture_gate_flags,
    detect_common_anti_patterns,
    detect_dependency_violations,
    scan_module_imports,
)


def test_scan_finds_imports_in_temp_project() -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "domain").mkdir()
        (root / "domain" / "x.py").write_text("from domain.y import z\n", encoding="utf-8")
        (root / "domain" / "y.py").write_text("X = 1\n", encoding="utf-8")
        pairs = scan_module_imports(str(root))
        assert any(p[1] == "domain" for p in pairs)


def test_domain_importing_infra_is_violation(tmp_path: Path) -> None:
    (tmp_path / "domain").mkdir()
    (tmp_path / "domain" / "bad.py").write_text(
        "from infrastructure.transports import x\n",
        encoding="utf-8",
    )
    v = detect_dependency_violations(str(tmp_path))
    assert any("infrastructure" in x.target_module for x in v)


def test_spider_transport_smell(tmp_path: Path) -> None:
    (tmp_path / "infrastructure" / "spiders").mkdir(parents=True)
    (tmp_path / "infrastructure" / "spiders" / "x.py").write_text(
        "from infrastructure.transports.foo import send\n",
        encoding="utf-8",
    )
    hits = detect_common_anti_patterns(str(tmp_path))
    assert any(h.get("anti_pattern") == "spider_contains_transport_logic" for h in hits)


def test_build_report_marks_acceptable_on_clean_tmp(tmp_path: Path) -> None:
    (tmp_path / "domain").mkdir()
    (tmp_path / "domain" / "ok.py").write_text("x = 1\n", encoding="utf-8")
    r = build_architecture_lint_report(str(tmp_path))
    assert r["acceptable"] is True


def test_gate_flags_keys() -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "domain").mkdir()
        (root / "domain" / "ok.py").write_text("a=1\n", encoding="utf-8")
        f = compute_architecture_gate_flags(str(root))
        assert set(f.keys()) == {
            "arch_dependency_gate_ok",
            "arch_anti_pattern_gate_ok",
            "architecture_lint_report_ok",
            "arch_core_import_gate_ok",
        }
