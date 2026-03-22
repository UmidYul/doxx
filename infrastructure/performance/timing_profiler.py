from __future__ import annotations

import random
import threading
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator, cast

from config.settings import settings
from domain.performance import PerformanceStage, StageTimingRecord, utcnow

_ALLOWED_STAGES: frozenset[str] = frozenset(
    {
        "crawl_request",
        "listing_parse",
        "product_parse",
        "normalize",
        "lifecycle_build",
        "batch_buffer",
        "crm_send",
        "crm_apply_parse",
        "reconcile",
        "observability",
    }
)


def _coerce_stage(stage: str) -> PerformanceStage:
    if stage in _ALLOWED_STAGES:
        return cast(PerformanceStage, stage)
    return cast(PerformanceStage, "observability")


@dataclass
class TimingToken:
    """Opaque handle from :func:`start_stage`; do not construct directly."""

    active: bool
    stage: PerformanceStage
    started_at: datetime
    start_mono: float
    store_name: str | None = None
    spider_name: str | None = None
    entity_key: str | None = None
    batch_id: str | None = None
    notes: list[str] = field(default_factory=list)


_lock = threading.Lock()
_buffer: deque[StageTimingRecord] = deque(maxlen=10_000)


def _buffer_maxlen() -> int:
    return int(getattr(settings, "STAGE_TIMING_BUFFER_MAX_RECORDS", 10_000) or 10_000)


def _ensure_buffer_maxlen() -> None:
    global _buffer
    mx = _buffer_maxlen()
    if _buffer.maxlen != mx:
        _buffer = deque(_buffer, maxlen=mx)


def reset_timing_profiler_for_tests() -> None:
    global _buffer
    with _lock:
        _buffer = deque(maxlen=_buffer_maxlen())


def start_stage(stage: str, **context: Any) -> TimingToken:
    if not getattr(settings, "ENABLE_PERFORMANCE_PROFILING", True):
        return TimingToken(False, "observability", utcnow(), time.monotonic())
    if not getattr(settings, "ENABLE_STAGE_TIMING", True):
        return TimingToken(False, _coerce_stage(stage), utcnow(), time.monotonic())
    st = _coerce_stage(stage)
    return TimingToken(
        True,
        st,
        utcnow(),
        time.monotonic(),
        store_name=_s(context.get("store_name")),
        spider_name=_s(context.get("spider_name")),
        entity_key=_s(context.get("entity_key")),
        batch_id=_s(context.get("batch_id")),
        notes=list(context.get("notes") or []) if isinstance(context.get("notes"), list) else [],
    )


def _s(v: Any) -> str | None:
    if v is None:
        return None
    t = str(v).strip()
    return t or None


def finish_stage(token: TimingToken) -> StageTimingRecord:
    finished = utcnow()
    if not token.active:
        return StageTimingRecord(
            stage=token.stage,
            started_at=token.started_at,
            finished_at=finished,
            duration_ms=0.0,
            store_name=token.store_name,
            spider_name=token.spider_name,
            entity_key=token.entity_key,
            batch_id=token.batch_id,
            notes=list(token.notes),
        )
    elapsed_ms = max(0.0, (time.monotonic() - token.start_mono) * 1000.0)
    rec = StageTimingRecord(
        stage=token.stage,
        started_at=token.started_at,
        finished_at=finished,
        duration_ms=elapsed_ms,
        store_name=token.store_name,
        spider_name=token.spider_name,
        entity_key=token.entity_key,
        batch_id=token.batch_id,
        notes=list(token.notes),
    )
    record_timing(rec)
    return rec


def record_timing(record: StageTimingRecord) -> None:
    if not getattr(settings, "ENABLE_PERFORMANCE_PROFILING", True):
        return
    try:
        from infrastructure.performance.perf_collector import ingest_timing_record

        ingest_timing_record(record)
    except Exception:
        pass
    if getattr(settings, "ENABLE_STAGE_TIMING", True):
        rate = float(getattr(settings, "PERFORMANCE_SAMPLE_RATE", 1.0) or 0.0)
        if rate >= 1.0 or random.random() <= rate:
            _ensure_buffer_maxlen()
            with _lock:
                _buffer.append(record)
    _emit_perf_slow_if_needed(record)


def _emit_perf_slow_if_needed(rec: StageTimingRecord) -> None:
    if not getattr(settings, "ENABLE_PERFORMANCE_PROFILING", True):
        return
    try:
        from infrastructure.performance.bottleneck_detector import (
            is_stage_slow,
            threshold_ms_for_performance_stage,
        )
        from infrastructure.observability import message_codes as mc
        from infrastructure.observability.event_logger import log_perf_event

        if not is_stage_slow(rec.stage, rec.duration_ms, settings):
            return
        log_perf_event(
            mc.PERF_STAGE_SLOW,
            stage=rec.stage,
            duration_ms=rec.duration_ms,
            store_name=rec.store_name,
            spider_name=rec.spider_name,
            entity_key=rec.entity_key,
            batch_id=rec.batch_id,
            severity="warning",
            threshold_ms=threshold_ms_for_performance_stage(rec.stage, settings),
        )
    except Exception:
        pass


def get_recent_timings(limit: int = 200) -> list[StageTimingRecord]:
    lim = max(0, int(limit))
    with _lock:
        if lim == 0:
            return []
        return list(_buffer)[-lim:]


@contextmanager
def timed_stage(stage: str, **context: Any) -> Iterator[None]:
    tok = start_stage(stage, **context)
    try:
        yield
    finally:
        finish_stage(tok)
