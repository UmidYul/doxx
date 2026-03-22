from __future__ import annotations

import tempfile
from pathlib import Path

from application.governance.docs_governance import (
    build_docs_coverage_report,
    check_docs_presence,
    compute_docs_governance_flags,
    list_required_docs,
    minimal_ownership_registry_for_ci,
)


def test_list_required_docs_non_empty() -> None:
    xs = list_required_docs()
    assert "docs/README.md" in xs
    assert "OWNERSHIP_MAP.md" in xs


def test_check_docs_presence_detects_missing() -> None:
    with tempfile.TemporaryDirectory() as d:
        missing = check_docs_presence(d)
        assert len(missing) == len(list_required_docs())


def test_build_docs_coverage_report_real_repo() -> None:
    root = Path(__file__).resolve().parents[2]
    r = build_docs_coverage_report(str(root), store_names=["mediapark", "uzum"], emit_structured_logs=False)
    assert r["coverage_pct"] == 100.0
    assert r["missing_required_docs"] == []
    assert r["stores_missing_playbooks"] == []


def test_compute_docs_governance_flags_passes_on_repo() -> None:
    root = Path(__file__).resolve().parents[2]
    f = compute_docs_governance_flags(str(root), store_names=["mediapark", "uzum"], emit_structured_logs=False)
    assert f["docs_required_present"] is True
    assert f["store_playbooks_for_enabled_stores"] is True
    assert f["knowledge_continuity_no_critical_gaps"] is True


def test_docs_gate_fails_when_required_missing() -> None:
    with tempfile.TemporaryDirectory() as d:
        f = compute_docs_governance_flags(d, store_names=[], min_coverage_pct=100.0, emit_structured_logs=False)
        assert f["docs_required_present"] is False
        assert f["docs_coverage_acceptable"] is False


def test_minimal_ownership_registry_covers_areas() -> None:
    reg = minimal_ownership_registry_for_ci()
    areas = {r.ownership_area for r in reg}
    assert "store_spiders" in areas
    assert "docs_fixtures_acceptance" in areas
