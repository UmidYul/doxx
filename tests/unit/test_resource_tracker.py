from __future__ import annotations

import pytest

from infrastructure.performance.resource_tracker import (
    build_runtime_state,
    decrement_inflight_batch,
    decrement_inflight_request,
    increment_inflight_batch,
    increment_inflight_request,
    reset_resource_tracker_for_tests,
    set_retryable_queue_size,
)


@pytest.fixture(autouse=True)
def _reset_tracker() -> None:
    reset_resource_tracker_for_tests()
    yield
    reset_resource_tracker_for_tests()


def test_counters_stay_non_negative_after_extra_decrements() -> None:
    decrement_inflight_request("s", "listing")
    decrement_inflight_batch("s")
    st = build_runtime_state("s")
    assert st.inflight_requests == 0
    assert st.inflight_batches == 0


def test_increment_decrement_listing_and_product() -> None:
    increment_inflight_request("st", "listing")
    increment_inflight_request("st", "product")
    st = build_runtime_state("st")
    assert st.inflight_requests == 2
    assert st.inflight_listing_requests == 1
    assert st.inflight_product_requests == 1
    decrement_inflight_request("st", "listing")
    decrement_inflight_request("st", "product")
    st2 = build_runtime_state("st")
    assert st2.inflight_requests == 0


def test_retryable_queue_tracked() -> None:
    set_retryable_queue_size("st", 42)
    st = build_runtime_state("st")
    assert st.queued_retryable_items == 42


def test_batch_inflight_round_trip() -> None:
    increment_inflight_batch("st")
    increment_inflight_batch("st")
    assert build_runtime_state("st").inflight_batches == 2
    decrement_inflight_batch("st")
    assert build_runtime_state("st").inflight_batches == 1
