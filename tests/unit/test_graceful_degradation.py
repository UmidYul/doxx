from __future__ import annotations

from application.performance.graceful_degradation import explain_degradation_mode, suggest_degradation_mode
from domain.resource_governance import BackpressureDecision, RuntimeResourceState


def test_nominal_is_none() -> None:
    bp = BackpressureDecision(
        apply_backpressure=False,
        store_name="s",
        reason="nominal",
        severity="warning",
        suggested_action="slow_down",
    )
    st = RuntimeResourceState(store_name="s")
    assert suggest_degradation_mode("s", st, bp) == "none"


def test_memory_critical_suggests_pause_store() -> None:
    bp = BackpressureDecision(
        apply_backpressure=True,
        store_name="s",
        reason="memory_critical",
        severity="critical",
        suggested_action="degrade_store",
    )
    st = RuntimeResourceState(store_name="s")
    assert suggest_degradation_mode("s", st, bp) == "pause_store"


def test_explain_returns_lines() -> None:
    bp = BackpressureDecision(
        apply_backpressure=True,
        store_name="s",
        reason="retryable_queue_critical",
        severity="critical",
        suggested_action="pause_batches",
    )
    st = RuntimeResourceState(store_name="s")
    lines = explain_degradation_mode("s", st, bp)
    assert any("suggested_mode" in x for x in lines)
