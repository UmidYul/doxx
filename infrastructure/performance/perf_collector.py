from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from config.settings import settings
from domain.performance import (
    RunPerformanceSnapshot,
    StageTimingRecord,
    StorePerformanceSnapshot,
    utcnow,
)
from infrastructure.performance.resource_snapshot import get_process_memory_mb


_COST_COUNTER_NAMES = frozenset(
    {
        "http_requests",
        "proxy_requests",
        "browser_pages",
        "retry_attempts",
        "products_applied",
        "crm_roundtrips",
        "batches",
        "products",
    }
)


@dataclass
class _StoreAgg:
    requests_total: int = 0
    products_total: int = 0
    batches_total: int = 0
    http_requests_total: int = 0
    proxy_requests_total: int = 0
    browser_pages_total: int = 0
    retry_attempts_total: int = 0
    products_applied_total: int = 0
    crm_roundtrips_total: int = 0
    request_ms_sum: float = 0.0
    request_n: int = 0
    product_parse_ms_sum: float = 0.0
    product_parse_n: int = 0
    normalize_ms_sum: float = 0.0
    normalize_n: int = 0
    crm_send_ms_sum: float = 0.0
    crm_send_n: int = 0
    batch_apply_ms_sum: float = 0.0
    batch_apply_n: int = 0
    batch_buffer_ms_sum: float = 0.0
    batch_buffer_n: int = 0
    reconcile_ms_sum: float = 0.0
    reconcile_n: int = 0
    observability_ms_sum: float = 0.0
    observability_n: int = 0
    lifecycle_ms_sum: float = 0.0
    lifecycle_n: int = 0
    listing_parse_ms_sum: float = 0.0
    listing_parse_n: int = 0
    first_seen: datetime | None = None
    last_seen: datetime | None = None


_lock = threading.Lock()
_stores: dict[str, _StoreAgg] = defaultdict(_StoreAgg)
_counters: dict[tuple[str, str | None], int] = defaultdict(int)
_run_id: str | None = None
_run_started_at: datetime | None = None
_stage_sum: dict[str, float] = defaultdict(float)
_stage_n: dict[str, int] = defaultdict(int)
_run_stores: list[str] = []


def reset_perf_collector_for_tests() -> None:
    global _run_id, _run_started_at, _run_stores
    with _lock:
        _stores.clear()
        _counters.clear()
        _run_id = None
        _run_started_at = None
        _stage_sum.clear()
        _stage_n.clear()
        _run_stores = []


def set_run_context(*, run_id: str, stores: list[str] | None = None) -> None:
    global _run_id, _run_started_at, _run_stores
    with _lock:
        _run_id = run_id
        _run_started_at = utcnow()
        _run_stores = list(stores or [])


def increment_counter(name: str, value: int = 1, store_name: str | None = None) -> None:
    perf_on = getattr(settings, "ENABLE_PERFORMANCE_PROFILING", True)
    cost_on = getattr(settings, "ENABLE_COST_EFFICIENCY_TRACKING", True)
    if not perf_on and not (cost_on and name in _COST_COUNTER_NAMES):
        return
    v = int(value)
    if v <= 0:
        return
    key = (name, (store_name.strip() if isinstance(store_name, str) else None))
    with _lock:
        _counters[key] += v
        st = store_name.strip() if isinstance(store_name, str) and store_name.strip() else None
        if st:
            agg = _stores[st]
            _touch(agg)
            if name == "requests":
                agg.requests_total += v
            elif name == "products":
                agg.products_total += v
            elif name == "batches":
                agg.batches_total += v
            elif name == "http_requests":
                agg.http_requests_total += v
            elif name == "proxy_requests":
                agg.proxy_requests_total += v
            elif name == "browser_pages":
                agg.browser_pages_total += v
            elif name == "retry_attempts":
                agg.retry_attempts_total += v
            elif name == "products_applied":
                agg.products_applied_total += v
            elif name == "crm_roundtrips":
                agg.crm_roundtrips_total += v


def record_scheduled_request_cost(store_name: str, meta: dict[str, Any]) -> None:
    """Count HTTP vs proxy vs browser for cost model (8C); call when a request is scheduled."""
    if not getattr(settings, "ENABLE_COST_EFFICIENCY_TRACKING", True):
        return
    st = (store_name or "").strip() or "unknown"
    sel = str(meta.get("access_mode_selected") or "plain").lower()
    if sel == "browser":
        increment_counter("browser_pages", 1, st)
    elif sel == "proxy":
        increment_counter("proxy_requests", 1, st)
    else:
        increment_counter("http_requests", 1, st)
    prior = int(meta.get("prior_failures", 0) or 0)
    if prior > 0:
        increment_counter("retry_attempts", 1, st)


def get_store_cost_counters(store_name: str) -> dict[str, int | float]:
    st = (store_name or "").strip() or "unknown"
    with _lock:
        agg = _stores.get(st) or _StoreAgg()
        return {
            "http_requests": agg.http_requests_total,
            "proxy_requests": agg.proxy_requests_total,
            "browser_pages": agg.browser_pages_total,
            "retry_attempts": agg.retry_attempts_total,
            "batch_flushes": agg.batches_total,
            "crm_roundtrips": agg.crm_roundtrips_total,
            "products_parsed": agg.products_total,
            "products_applied": agg.products_applied_total,
            "normalization_units": float(agg.normalize_n),
            "diagnostic_units": float(agg.observability_n),
        }


def export_all_store_cost_counters() -> dict[str, dict[str, int | float]]:
    with _lock:
        keys = sorted(set(_stores.keys()) | set(_run_stores))
    return {k: get_store_cost_counters(k) for k in keys}


def _touch(agg: _StoreAgg) -> None:
    now = utcnow()
    if agg.first_seen is None:
        agg.first_seen = now
    agg.last_seen = now


def _avg(sum_ms: float, n: int) -> float | None:
    if n <= 0:
        return None
    return sum_ms / float(n)


def record_duration(stage: str, duration_ms: float, store_name: str | None = None) -> None:
    if not getattr(settings, "ENABLE_PERFORMANCE_PROFILING", True):
        return
    d = float(duration_ms)
    if d < 0:
        d = 0.0
    st = store_name.strip() if isinstance(store_name, str) and store_name.strip() else None
    with _lock:
        _stage_sum[stage] += d
        _stage_n[stage] += 1
        if st:
            agg = _stores[st]
            _touch(agg)
            if stage == "crawl_request":
                agg.request_ms_sum += d
                agg.request_n += 1
            elif stage == "product_parse":
                agg.product_parse_ms_sum += d
                agg.product_parse_n += 1
            elif stage == "normalize":
                agg.normalize_ms_sum += d
                agg.normalize_n += 1
            elif stage == "crm_send":
                agg.crm_send_ms_sum += d
                agg.crm_send_n += 1
            elif stage == "crm_apply_parse":
                agg.batch_apply_ms_sum += d
                agg.batch_apply_n += 1
            elif stage == "batch_buffer":
                agg.batch_buffer_ms_sum += d
                agg.batch_buffer_n += 1
            elif stage == "reconcile":
                agg.reconcile_ms_sum += d
                agg.reconcile_n += 1
            elif stage == "observability":
                agg.observability_ms_sum += d
                agg.observability_n += 1
            elif stage == "lifecycle_build":
                agg.lifecycle_ms_sum += d
                agg.lifecycle_n += 1
            elif stage == "listing_parse":
                agg.listing_parse_ms_sum += d
                agg.listing_parse_n += 1


def ingest_timing_record(record: StageTimingRecord) -> None:
    """Hook from :func:`infrastructure.performance.timing_profiler.record_timing`."""
    record_duration(
        record.stage,
        record.duration_ms,
        store_name=record.store_name,
    )


def build_store_snapshot(store_name: str) -> StorePerformanceSnapshot:
    with _lock:
        agg = _stores.get(store_name) or _StoreAgg()
        mem = get_process_memory_mb()
        elapsed_min = _elapsed_minutes(agg)
        ppm = _rate_per_min(agg.products_total, elapsed_min)
        bpm = _rate_per_min(agg.batches_total, elapsed_min)
        snap = StorePerformanceSnapshot(
            store_name=store_name,
            requests_total=agg.requests_total,
            products_total=agg.products_total,
            batches_total=agg.batches_total,
            avg_request_ms=_avg(agg.request_ms_sum, agg.request_n),
            avg_product_parse_ms=_avg(agg.product_parse_ms_sum, agg.product_parse_n),
            avg_normalize_ms=_avg(agg.normalize_ms_sum, agg.normalize_n),
            avg_crm_send_ms=_avg(agg.crm_send_ms_sum, agg.crm_send_n),
            avg_batch_apply_ms=_avg(agg.batch_apply_ms_sum, agg.batch_apply_n),
            products_per_minute=ppm,
            batches_per_minute=bpm,
            memory_estimate_mb=mem,
            status="normal",
        )
    return snap


def _elapsed_minutes(agg: _StoreAgg) -> float | None:
    if agg.first_seen is None or agg.last_seen is None:
        return None
    dt = (agg.last_seen - agg.first_seen).total_seconds() / 60.0
    if dt <= 1e-9:
        return None
    return dt


def _rate_per_min(count: int, elapsed_min: float | None) -> float | None:
    if elapsed_min is None or elapsed_min <= 0:
        return None
    return float(count) / float(elapsed_min)


def build_run_snapshot(run_id: str, stores: list[str]) -> RunPerformanceSnapshot:
    from config.settings import settings as stg

    started = utcnow()
    store_snaps: list[StorePerformanceSnapshot] = []
    stage_avgs: dict[str, float] = {}
    with _lock:
        started = _run_started_at or started
        for s in sorted(set(stores)):
            store_snaps.append(_build_store_snapshot_locked(s))
        for st, sm in _stage_sum.items():
            n = _stage_n.get(st, 0)
            if n > 0:
                stage_avgs[st] = sm / float(n)
    slowest = sorted(stage_avgs.keys(), key=lambda k: stage_avgs[k], reverse=True)[:5]
    if getattr(stg, "ENABLE_STORE_PERFORMANCE_SNAPSHOT", True):
        from infrastructure.performance.bottleneck_detector import classify_store_performance

        store_snaps = [
            snap.model_copy(update={"status": classify_store_performance(snap, stg)})
            for snap in store_snaps
        ]
    return RunPerformanceSnapshot(
        run_id=run_id,
        started_at=started,
        stores=list(stores),
        stage_averages_ms=stage_avgs,
        store_snapshots=store_snaps,
        slowest_stages=slowest,
        bottlenecks=[],
        overall_status="normal",
    )


def _build_store_snapshot_locked(store_name: str) -> StorePerformanceSnapshot:
    agg = _stores.get(store_name) or _StoreAgg()
    mem = get_process_memory_mb()
    elapsed_min = _elapsed_minutes(agg)
    ppm = _rate_per_min(agg.products_total, elapsed_min)
    bpm = _rate_per_min(agg.batches_total, elapsed_min)
    return StorePerformanceSnapshot(
        store_name=store_name,
        requests_total=agg.requests_total,
        products_total=agg.products_total,
        batches_total=agg.batches_total,
        avg_request_ms=_avg(agg.request_ms_sum, agg.request_n),
        avg_product_parse_ms=_avg(agg.product_parse_ms_sum, agg.product_parse_n),
        avg_normalize_ms=_avg(agg.normalize_ms_sum, agg.normalize_n),
        avg_crm_send_ms=_avg(agg.crm_send_ms_sum, agg.crm_send_n),
        avg_batch_apply_ms=_avg(agg.batch_apply_ms_sum, agg.batch_apply_n),
        products_per_minute=ppm,
        batches_per_minute=bpm,
        memory_estimate_mb=mem,
        status="normal",
    )


def trim_if_needed() -> None:
    """No-op placeholder; in-memory aggregates are compact. Timing buffer trims in timing_profiler."""
    return


def get_perf_collector() -> PerfCollector:
    return _collector_singleton


class PerfCollector:
    """Namespace for tests and explicit calls; state is module-level."""

    increment_counter = staticmethod(increment_counter)
    record_duration = staticmethod(record_duration)
    record_scheduled_request_cost = staticmethod(record_scheduled_request_cost)
    get_store_cost_counters = staticmethod(get_store_cost_counters)
    export_all_store_cost_counters = staticmethod(export_all_store_cost_counters)
    ingest_timing_record = staticmethod(ingest_timing_record)
    build_store_snapshot = staticmethod(build_store_snapshot)
    build_run_snapshot = staticmethod(build_run_snapshot)
    trim_if_needed = staticmethod(trim_if_needed)
    set_run_context = staticmethod(set_run_context)


_collector_singleton = PerfCollector()
