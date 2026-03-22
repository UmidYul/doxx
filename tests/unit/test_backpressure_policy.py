from __future__ import annotations

from types import SimpleNamespace

import pytest

from application.performance.backpressure_policy import decide_backpressure, decide_throttle_adjustment
from domain.resource_governance import RuntimeResourceState, StoreResourceBudget


def _budget() -> StoreResourceBudget:
    return StoreResourceBudget(
        store_name="t",
        max_concurrent_requests=10,
        max_listing_requests=6,
        max_product_requests=6,
        max_batch_inflight=4,
        max_retryable_queue=200,
        max_browser_pages=2,
        max_proxy_requests=4,
        max_memory_mb=512,
        notes=[],
    )


def test_retryable_queue_elevated_triggers_backpressure() -> None:
    st = RuntimeResourceState(store_name="t", queued_retryable_items=120)
    s = SimpleNamespace(
        ENABLE_BACKPRESSURE_POLICY=True,
        BACKPRESSURE_RETRYABLE_QUEUE_WARNING=100,
        BACKPRESSURE_RETRYABLE_QUEUE_CRITICAL=200,
        BACKPRESSURE_MEMORY_WARNING_MB=384,
        BACKPRESSURE_MEMORY_CRITICAL_MB=512,
        GLOBAL_MAX_MEMORY_MB=512,
        BACKPRESSURE_BATCH_INFLIGHT_WARNING=3,
        BACKPRESSURE_BATCH_INFLIGHT_CRITICAL=4,
    )
    d = decide_backpressure("t", st, _budget(), s)
    assert d.apply_backpressure
    assert d.suggested_action == "slow_down"


def test_memory_critical_degrade_store() -> None:
    st = RuntimeResourceState(store_name="t", memory_mb=600.0)
    s = SimpleNamespace(
        ENABLE_BACKPRESSURE_POLICY=True,
        BACKPRESSURE_MEMORY_WARNING_MB=384,
        BACKPRESSURE_MEMORY_CRITICAL_MB=512,
        GLOBAL_MAX_MEMORY_MB=512,
        BACKPRESSURE_RETRYABLE_QUEUE_WARNING=100,
        BACKPRESSURE_RETRYABLE_QUEUE_CRITICAL=200,
        BACKPRESSURE_BATCH_INFLIGHT_WARNING=3,
        BACKPRESSURE_BATCH_INFLIGHT_CRITICAL=4,
    )
    d = decide_backpressure("t", st, _budget(), s)
    assert d.severity == "critical"
    assert d.suggested_action == "degrade_store"


def test_batch_inflight_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    from config.settings import settings

    monkeypatch.setattr(settings, "ENABLE_BACKPRESSURE_POLICY", True)
    st = RuntimeResourceState(store_name="t", inflight_batches=3)
    d = decide_backpressure("t", st, _budget(), settings)
    assert d.apply_backpressure
    assert d.suggested_action == "slow_down"


def test_throttle_when_browser_saturated(monkeypatch: pytest.MonkeyPatch) -> None:
    from config.settings import settings

    monkeypatch.setattr(settings, "GLOBAL_MAX_BROWSER_PAGES", 2)
    b = _budget()
    st = RuntimeResourceState(store_name="t", active_browser_pages=2)
    t = decide_throttle_adjustment("t", st, b, settings)
    assert t.throttle
    assert t.mode == "browser"


def test_throttle_when_proxy_saturated(monkeypatch: pytest.MonkeyPatch) -> None:
    from config.settings import settings

    monkeypatch.setattr(settings, "GLOBAL_MAX_PROXY_REQUESTS", 4)
    b = _budget()
    st = RuntimeResourceState(store_name="t", active_proxy_requests=4)
    t = decide_throttle_adjustment("t", st, b, settings)
    assert t.throttle
    assert t.mode == "proxy"
