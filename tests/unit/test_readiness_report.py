from __future__ import annotations

from pathlib import Path

from application.readiness.evidence_collector import collect_readiness_evidence
from application.readiness.gap_assessor import assess_readiness_gaps, update_checklist_status_from_evidence
from application.readiness.readiness_registry import get_default_readiness_checklist
from application.readiness.readiness_report import (
    build_human_readiness_report,
    build_production_readiness_report,
    compute_readiness_gate_flags,
    summarize_domain_statuses,
)
from application.release.release_gate_evaluator import evaluate_release_gates


def test_human_report_contains_sections() -> None:
    root = str(Path(__file__).resolve().parents[2])
    ev = collect_readiness_evidence(root)
    c = update_checklist_status_from_evidence(
        get_default_readiness_checklist(),
        ev,
        root,
        store_names=["mediapark", "uzum"],
    )
    gaps = assess_readiness_gaps(c, ev)
    rep = build_production_readiness_report(c, gaps, ev)
    text = build_human_readiness_report(rep)
    assert "Overall:" in text
    assert "Next actions:" in text
    assert "Go-live policy" in text
    dom = summarize_domain_statuses(rep)
    assert "crawl" in dom


def test_compute_readiness_gate_flags_repo() -> None:
    root = str(Path(__file__).resolve().parents[2])
    f = compute_readiness_gate_flags(root, store_names=["mediapark", "uzum"])
    assert all(f.values())


def test_release_gate_blocks_on_readiness_flag() -> None:
    gates = evaluate_release_gates({"readiness_no_critical_blocking_gaps": False})
    rg = next(g for g in gates if g.gate_name == "readiness_no_blocking_gaps")
    assert rg.passed is False
