from __future__ import annotations

from infrastructure.observability.runbook_registry import build_runbook_steps, get_runbook_for_domain


def test_runbook_steps_per_domain():
    for dom in (
        "store_access",
        "crawl_quality",
        "normalization_quality",
        "delivery_transport",
        "crm_apply",
        "reconciliation",
        "internal",
    ):
        steps = build_runbook_steps(dom, "high")  # type: ignore[arg-type]
        assert steps, dom
        assert all(s.step_order > 0 for s in steps)


def test_store_access_runbook_mentions_block():
    plan = get_runbook_for_domain("store_access", "high")
    text = " ".join(s.instruction for s in plan.steps).lower()
    assert "block" in text or "ban" in text


def test_get_runbook_has_final_recommendation():
    p = get_runbook_for_domain("delivery_transport", "critical")
    assert p.final_recommendation == "retry_batch_once"
