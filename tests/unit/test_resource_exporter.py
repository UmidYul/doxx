from __future__ import annotations

from domain.resource_governance import BackpressureDecision, RuntimeResourceState, StoreResourceBudget
from infrastructure.performance.resource_exporter import (
    build_backpressure_payload,
    build_resource_state_payload,
    build_store_budget_payload,
)


def test_build_resource_state_payload_compact() -> None:
    st = RuntimeResourceState(
        store_name="x",
        inflight_requests=1,
        inflight_batches=0,
        queued_retryable_items=3,
        memory_mb=100.0,
    )
    p = build_resource_state_payload(st)
    assert p["kind"] == "runtime_resource_state_v1"
    assert p["store_name"] == "x"
    assert len(p) <= 12


def test_build_store_budget_payload() -> None:
    b = StoreResourceBudget(
        store_name="x",
        max_concurrent_requests=4,
        max_listing_requests=2,
        max_product_requests=2,
        max_batch_inflight=1,
        max_retryable_queue=50,
        max_browser_pages=1,
        max_proxy_requests=2,
        max_memory_mb=256,
        notes=["n"],
    )
    p = build_store_budget_payload(b)
    assert p["kind"] == "store_resource_budget_v1"
    assert p["notes"] == ["n"]


def test_build_backpressure_payload() -> None:
    d = BackpressureDecision(
        apply_backpressure=True,
        store_name="s",
        reason="r",
        severity="high",
        suggested_action="slow_down",
    )
    p = build_backpressure_payload(d)
    assert p["apply_backpressure"] is True
    assert p["suggested_action"] == "slow_down"
