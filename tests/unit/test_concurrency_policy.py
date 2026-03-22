from __future__ import annotations

import pytest

from application.performance.concurrency_policy import (
    decide_batch_admission,
    decide_browser_admission,
    decide_proxy_admission,
    decide_request_admission,
)
from domain.resource_governance import RuntimeResourceState, StoreResourceBudget
from infrastructure.performance.resource_tracker import increment_inflight_batch, reset_resource_tracker_for_tests


def _budget(**kwargs: object) -> StoreResourceBudget:
    base = dict(
        store_name="t",
        max_concurrent_requests=10,
        max_listing_requests=6,
        max_product_requests=6,
        max_batch_inflight=3,
        max_retryable_queue=200,
        max_browser_pages=2,
        max_proxy_requests=4,
        max_memory_mb=512,
        notes=[],
    )
    base.update(kwargs)
    return StoreResourceBudget(**base)


@pytest.fixture(autouse=True)
def _reset_tracker() -> None:
    reset_resource_tracker_for_tests()
    yield
    reset_resource_tracker_for_tests()


def test_request_admission_blocked_at_store_concurrent_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    from config.settings import settings

    monkeypatch.setattr(settings, "GLOBAL_MAX_CONCURRENT_REQUESTS", 100)
    b = _budget(max_concurrent_requests=2)
    st = RuntimeResourceState(store_name="t", inflight_requests=2)
    d = decide_request_admission("t", "listing", "http", st, b)
    assert not d.allowed
    assert "concurrent" in d.reason


def test_listing_vs_product_caps_distinct(monkeypatch: pytest.MonkeyPatch) -> None:
    from config.settings import settings

    monkeypatch.setattr(settings, "GLOBAL_MAX_CONCURRENT_REQUESTS", 100)
    b = _budget(max_listing_requests=1, max_product_requests=5, max_concurrent_requests=10)
    st = RuntimeResourceState(store_name="t", inflight_listing_requests=1, inflight_requests=1)
    d = decide_request_admission("t", "listing", "http", st, b)
    assert not d.allowed


def test_browser_admission_blocked_when_budget_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    from config.settings import settings

    monkeypatch.setattr(settings, "GLOBAL_MAX_BROWSER_PAGES", 4)
    b = _budget(max_browser_pages=1)
    st = RuntimeResourceState(store_name="t", active_browser_pages=1)
    d = decide_browser_admission("t", st, b)
    assert not d.allowed


def test_proxy_admission_blocked_when_budget_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    from config.settings import settings

    monkeypatch.setattr(settings, "GLOBAL_MAX_PROXY_REQUESTS", 8)
    b = _budget(max_proxy_requests=1)
    st = RuntimeResourceState(store_name="t", active_proxy_requests=1)
    d = decide_proxy_admission("t", st, b)
    assert not d.allowed


def test_batch_admission_respects_inflight_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    from config.settings import settings

    monkeypatch.setattr(settings, "GLOBAL_MAX_INFLIGHT_BATCHES", 8)
    b = _budget(max_batch_inflight=1)
    st = RuntimeResourceState(store_name="t", inflight_batches=1)
    d = decide_batch_admission("t", st, b)
    assert not d.allowed


def test_global_and_store_batch_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    from config.settings import settings

    monkeypatch.setattr(settings, "GLOBAL_MAX_INFLIGHT_BATCHES", 1)
    b = _budget(max_batch_inflight=10)
    increment_inflight_batch("other")
    st = RuntimeResourceState(store_name="t", inflight_batches=0)
    d = decide_batch_admission("t", st, b)
    assert not d.allowed
    assert "global" in d.reason


def test_retryable_queue_pressure_blocks_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    from config.settings import settings

    monkeypatch.setattr(settings, "BACKPRESSURE_RETRYABLE_QUEUE_CRITICAL", 50)
    monkeypatch.setattr(settings, "GLOBAL_MAX_RETRYABLE_QUEUE", 200)
    b = _budget(max_retryable_queue=40)
    st = RuntimeResourceState(store_name="t", queued_retryable_items=50)
    d = decide_request_admission("t", "product", "http", st, b)
    assert not d.allowed
    assert "retryable" in d.reason
