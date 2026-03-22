from __future__ import annotations

from datetime import UTC, datetime

from domain.observability import BatchTraceRecord, SyncCorrelationContext, SyncTraceRecord

from infrastructure.observability.trace_collector import TraceCollector


def _corr() -> SyncCorrelationContext:
    return SyncCorrelationContext(run_id="r1", spider_name="s", store_name="st")


def test_trace_buffer_bounded_and_trims_via_deque_maxlen():
    tc = TraceCollector(max_records=3)
    tc.set_run_context(run_id="r1", stores=["st"])
    for i in range(5):
        tc.record_trace(
            SyncTraceRecord(
                stage="crawl",
                severity="info",
                message_code=f"C{i}",
                correlation=_corr(),
            )
        )
    recent = tc.get_recent_traces(100)
    assert len(recent) == 3
    assert recent[-1].message_code == "C4"


def test_batch_traces_and_health_snapshot_merge_counters():
    tc = TraceCollector(max_records=100)
    tc.set_run_context(run_id="r1", stores=["st"])
    tc.record_batch_trace(
        BatchTraceRecord(
            batch_id="b1",
            run_id="r1",
            store_name="st",
            created_at=datetime.now(UTC),
            flushed_at=datetime.now(UTC),
            item_count=2,
            success_count=1,
            rejected_count=1,
            retryable_count=0,
            ignored_count=0,
            transport_failed=False,
            http_status=200,
            notes=["t"],
        )
    )
    batches = tc.get_recent_batch_traces(10)
    assert len(batches) == 1
    assert batches[0].batch_id == "b1"
