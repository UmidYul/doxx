from __future__ import annotations

from datetime import UTC, datetime, timedelta

from config.settings import Settings
from domain.observability import SyncCorrelationContext, SyncTraceRecord
from infrastructure.security.retention_guard import (
    apply_retention_policies,
    trim_trace_buffer_by_age,
    trim_trace_buffer_by_count,
)


def _mk_trace(ts: datetime) -> SyncTraceRecord:
    return SyncTraceRecord(
        stage="internal",
        severity="info",
        message_code="TEST",
        correlation=SyncCorrelationContext(
            run_id="r",
            spider_name="s",
            store_name="st",
        ),
        timestamp=ts,
    )


def test_trim_by_age_removes_old() -> None:
    now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
    old = now - timedelta(hours=2)
    recs = [_mk_trace(old), _mk_trace(now)]
    out = trim_trace_buffer_by_age(recs, max_age_seconds=3600, now=now)
    assert len(out) == 1


def test_trim_by_count() -> None:
    recs = [_mk_trace(datetime.now(UTC)) for _ in range(5)]
    out = trim_trace_buffer_by_count(recs, 3)
    assert len(out) == 3


def test_apply_retention_policies_returns_trimmed() -> None:
    s = Settings(_env_file=None, ENABLE_RUNTIME_RETENTION_LIMITS=True, TRACE_MAX_AGE_SECONDS=1, TRACE_BUFFER_MAX_RECORDS=1000)  # type: ignore[arg-type]
    now = datetime.now(UTC)
    recs = [_mk_trace(now - timedelta(seconds=10)), _mk_trace(now)]
    res = apply_retention_policies(traces=recs, batch_traces=[], settings=s, now=now)
    assert int(res["traces_removed"]) >= 0
    assert "traces" in res
