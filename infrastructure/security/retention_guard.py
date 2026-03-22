from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

from config.settings import Settings, settings as app_settings

T = TypeVar("T")


def trim_trace_buffer_by_age(records: list[T], max_age_seconds: int, *, now: datetime | None = None) -> list[T]:
    if max_age_seconds <= 0 or not records:
        return list(records)
    cutoff = (now or datetime.now(UTC)) - timedelta(seconds=max_age_seconds)
    out: list[T] = []
    for r in records:
        ts = getattr(r, "timestamp", None)
        if ts is None:
            out.append(r)
            continue
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            if ts >= cutoff:
                out.append(r)
        else:
            out.append(r)
    return out


def trim_trace_buffer_by_count(records: list[T], max_records: int | None) -> list[T]:
    if max_records is None or max_records <= 0:
        return list(records)
    if len(records) <= max_records:
        return list(records)
    return list(records)[-max_records:]


def trim_batch_traces(
    batches: list[Any],
    *,
    max_age_seconds: int,
    max_records: int | None,
    now: datetime | None = None,
) -> list[Any]:
    if not batches:
        return []
    cutoff = (now or datetime.now(UTC)) - timedelta(seconds=max_age_seconds) if max_age_seconds > 0 else None
    filtered: list[Any] = []
    for b in batches:
        ts = getattr(b, "created_at", None)
        if cutoff is None or ts is None:
            filtered.append(b)
            continue
        if isinstance(ts, datetime):
            t2 = ts if ts.tzinfo else ts.replace(tzinfo=UTC)
            if t2 >= cutoff:
                filtered.append(b)
        else:
            filtered.append(b)
    return trim_trace_buffer_by_count(filtered, max_records)


def trim_diagnostic_samples(samples: list[Any], max_items: int) -> list[Any]:
    if max_items <= 0:
        return []
    return list(samples)[:max_items]


def apply_retention_policies(
    *,
    traces: list[Any],
    batch_traces: list[Any],
    settings: Settings | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    s = settings or app_settings
    if not getattr(s, "ENABLE_RUNTIME_RETENTION_LIMITS", True):
        return {
            "traces_kept": len(traces),
            "batches_kept": len(batch_traces),
            "traces_removed": 0,
            "batches_removed": 0,
        }
    t_max_age = int(getattr(s, "TRACE_MAX_AGE_SECONDS", 3600) or 0)
    b_max_age = int(getattr(s, "BATCH_TRACE_MAX_AGE_SECONDS", 3600) or 0)
    max_r = getattr(s, "TRACE_BUFFER_MAX_RECORDS", None)
    try:
        max_records = int(max_r) if max_r is not None else None
    except (TypeError, ValueError):
        max_records = None

    n_t0, n_b0 = len(traces), len(batch_traces)
    t1 = trim_trace_buffer_by_age(traces, t_max_age, now=now)
    t2 = trim_trace_buffer_by_count(t1, max_records)
    b1 = trim_batch_traces(batch_traces, max_age_seconds=b_max_age, max_records=min(500, max_records or 500), now=now)
    return {
        "artifact_name": "trace_and_batch_buffers",
        "traces_kept": len(t2),
        "batches_kept": len(b1),
        "traces_removed": n_t0 - len(t2),
        "batches_removed": n_b0 - len(b1),
        "max_age_seconds": t_max_age,
        "max_records": max_records,
        "traces": t2,
        "batch_traces": b1,
    }
