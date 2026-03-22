from __future__ import annotations

from infrastructure.observability.correlation import (
    build_batch_id,
    build_correlation_context,
    build_run_id,
)
from infrastructure.observability.trace_collector import (
    get_trace_collector,
    reset_trace_collector_for_tests,
)


def test_build_run_id_unique_per_call():
    a = build_run_id("mediapark")
    b = build_run_id("mediapark")
    assert a != b
    assert a.startswith("mediapark:")
    assert b.startswith("mediapark:")


def test_build_batch_id_deterministic():
    assert build_batch_id("run:1", 3) == "run:1:batch:3"
    assert build_batch_id("run:1", 3) == build_batch_id("run:1", 3)


def test_build_correlation_context_uses_trace_run_id():
    reset_trace_collector_for_tests()
    get_trace_collector().set_run_context(run_id="fixed-run", stores=["s1"])
    ctx = build_correlation_context("spider1", "store_a", source_url="https://x/y")
    assert ctx.run_id == "fixed-run"
    assert ctx.spider_name == "spider1"
    assert ctx.store_name == "store_a"
    assert ctx.source_url == "https://x/y"
    assert ctx.batch_id is None

    ctx2 = build_correlation_context(
        "spider1",
        "store_a",
        run_id="override",
        entity_key="ek",
        event_id="e1",
        batch_id="b1",
    )
    assert ctx2.run_id == "override"
    assert ctx2.entity_key == "ek"
    assert ctx2.event_id == "e1"
    assert ctx2.batch_id == "b1"
