from __future__ import annotations

from pathlib import Path

from application.readiness.evidence_collector import collect_readiness_evidence
from application.readiness.gap_assessor import (
    assess_readiness_gaps,
    infer_blocking_gaps,
    update_checklist_status_from_evidence,
)
from application.readiness.readiness_registry import get_default_readiness_checklist


def test_update_checklist_all_ready_on_repo() -> None:
    root = str(Path(__file__).resolve().parents[2])
    ev = collect_readiness_evidence(root)
    c = update_checklist_status_from_evidence(
        get_default_readiness_checklist(),
        ev,
        root,
        store_names=["mediapark", "uzum"],
    )
    assert all(i.status == "ready" for i in c)


def test_missing_paths_create_gaps(tmp_path: Path) -> None:
    ev: list = []
    c = update_checklist_status_from_evidence(get_default_readiness_checklist(), ev, str(tmp_path), store_names=[])
    gaps = assess_readiness_gaps(c, ev)
    assert len(gaps) > 0
    blocking = infer_blocking_gaps(gaps)
    assert any(g.blocking for g in blocking)


def test_security_partial_is_blocking_gap() -> None:
    from domain.production_readiness import ReadinessChecklistItem

    items = [
        ReadinessChecklistItem(
            domain="security",
            item_code="sec.redaction",
            title="t",
            description="d",
            required=True,
            status="partial",
            risk_if_missing="critical",
            evidence_required=["unit_tests"],
        )
    ]
    gaps = assess_readiness_gaps(items, [])
    assert gaps and gaps[0].blocking
