from __future__ import annotations

from pathlib import Path

from application.readiness.evidence_collector import (
    collect_readiness_evidence,
    find_config_evidence,
    find_docs_evidence,
    find_test_evidence,
)


def test_collect_evidence_on_repo() -> None:
    root = str(Path(__file__).resolve().parents[2])
    ev = collect_readiness_evidence(root)
    assert ev
    types = {e.evidence_type for e in ev}
    assert "unit_tests" in types
    assert "docs" in types


def test_find_test_evidence_minimal_tmp(tmp_path: Path) -> None:
    ev = find_test_evidence(str(tmp_path))
    assert isinstance(ev, list)


def test_find_docs_and_config_on_repo() -> None:
    root = str(Path(__file__).resolve().parents[2])
    d = find_docs_evidence(root)
    c = find_config_evidence(root)
    assert any(e.valid for e in d)
    assert any(e.valid for e in c)
