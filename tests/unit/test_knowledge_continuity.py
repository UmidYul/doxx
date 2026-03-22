from __future__ import annotations

from pathlib import Path

from application.governance.docs_governance import (
    build_docs_coverage_report,
    default_knowledge_assets,
    minimal_ownership_registry_for_ci,
)
from application.governance.knowledge_continuity import (
    build_knowledge_continuity_report,
    recommend_missing_docs,
    summarize_knowledge_risk,
)
def test_knowledge_continuity_report_with_registry() -> None:
    root = Path(__file__).resolve().parents[2]
    cov = build_docs_coverage_report(str(root), store_names=["mediapark", "uzum"])
    reg = minimal_ownership_registry_for_ci()
    assets = default_knowledge_assets()
    rep = build_knowledge_continuity_report(reg, assets, cov, emit_structured_logs=False)
    assert rep["risk_level"] in ("low", "medium", "high")
    assert rep["ownership_registry_empty"] is False
    assert not rep["uncovered_ownership_areas"]


def test_recommend_missing_docs_empty_when_complete() -> None:
    root = Path(__file__).resolve().parents[2]
    cov = build_docs_coverage_report(str(root), store_names=["mediapark"])
    rec = recommend_missing_docs(cov, store_names=["mediapark"])
    assert rec == []


def test_summarize_knowledge_risk_string() -> None:
    s = summarize_knowledge_risk(
        {"risk_level": "high", "missing_key_docs": ["a"], "stores_without_playbooks": [], "uncovered_ownership_areas": []}
    )
    assert "high" in s


def test_uncovered_areas_when_no_registry() -> None:
    root = Path(__file__).resolve().parents[2]
    cov = build_docs_coverage_report(str(root), store_names=["mediapark", "uzum"])
    rep = build_knowledge_continuity_report(None, [], cov, emit_structured_logs=False)
    assert rep["ownership_registry_empty"] is True
    assert len(rep["uncovered_ownership_areas"]) >= 1


def test_release_gate_fails_docs_policy() -> None:
    from application.release.release_gate_evaluator import evaluate_release_gates

    gates = evaluate_release_gates({"docs_required_present": False})
    doc_g = next(g for g in gates if g.gate_name == "docs_required")
    assert doc_g.passed is False
    assert doc_g.severity == "critical"
