from __future__ import annotations

from typing import Any, Literal, cast

from domain.performance import BottleneckSignal, PerformanceStage, RunPerformanceSnapshot, StorePerformanceSnapshot


def is_stage_slow(stage: str, duration_ms: float, settings: Any) -> bool:
    d = float(duration_ms)
    if stage == "crawl_request":
        return d > float(getattr(settings, "PERF_SLOW_REQUEST_MS", 3000))
    if stage == "product_parse":
        return d > float(getattr(settings, "PERF_SLOW_PRODUCT_PARSE_MS", 1000))
    if stage == "normalize":
        return d > float(getattr(settings, "PERF_SLOW_NORMALIZE_MS", 500))
    if stage == "crm_send":
        return d > float(getattr(settings, "PERF_SLOW_CRM_SEND_MS", 2000))
    if stage in ("crm_apply_parse", "batch_buffer"):
        return d > float(getattr(settings, "PERF_SLOW_BATCH_APPLY_MS", 3000))
    if stage == "reconcile":
        return d > float(getattr(settings, "PERF_SLOW_BATCH_APPLY_MS", 3000))
    if stage == "observability":
        return d > float(getattr(settings, "PERF_SLOW_NORMALIZE_MS", 500))
    return d > float(getattr(settings, "PERF_SLOW_CRM_SEND_MS", 2000))


def classify_store_performance(snapshot: StorePerformanceSnapshot, settings: Any) -> str:
    mem = snapshot.memory_estimate_mb
    crit = float(getattr(settings, "PERF_CRITICAL_MEMORY_MB", 512))
    if mem is not None and mem >= crit:
        return "critical"
    if snapshot.avg_request_ms and snapshot.avg_request_ms > float(
        getattr(settings, "PERF_SLOW_REQUEST_MS", 3000)
    ):
        return "slow"
    if snapshot.avg_normalize_ms and snapshot.avg_normalize_ms > float(
        getattr(settings, "PERF_SLOW_NORMALIZE_MS", 500)
    ):
        return "slow"
    if snapshot.avg_crm_send_ms and snapshot.avg_crm_send_ms > float(
        getattr(settings, "PERF_SLOW_CRM_SEND_MS", 2000)
    ):
        return "slow"
    if snapshot.avg_batch_apply_ms and snapshot.avg_batch_apply_ms > float(
        getattr(settings, "PERF_SLOW_BATCH_APPLY_MS", 3000)
    ):
        return "slow"
    if (
        snapshot.products_per_minute is not None
        and snapshot.products_total >= 10
        and snapshot.products_per_minute < 2.0
    ):
        return "slow"
    return "normal"


def detect_bottlenecks(
    run_snapshot: RunPerformanceSnapshot,
    settings: Any,
) -> list[BottleneckSignal]:
    out: list[BottleneckSignal] = []
    crit_mem = float(getattr(settings, "PERF_CRITICAL_MEMORY_MB", 512))

    for snap in run_snapshot.store_snapshots:
        st = snap.store_name
        status = classify_store_performance(snap, settings)
        snap_status = status
        if snap_status == "critical":
            if snap.memory_estimate_mb is not None:
                out.append(
                    BottleneckSignal(
                        stage="observability",
                        store_name=st,
                    severity="critical",
                    observed_ms=float(snap.memory_estimate_mb or 0.0),
                    threshold_ms=crit_mem,
                    reason="process_memory_estimate_exceeds_critical_threshold",
                )
            )

        if snap.avg_request_ms and snap.avg_request_ms > float(
            getattr(settings, "PERF_SLOW_REQUEST_MS", 3000)
        ):
            out.append(
                BottleneckSignal(
                    stage="crawl_request",
                    store_name=st,
                    severity="high" if snap_status != "normal" else "warning",
                    observed_ms=snap.avg_request_ms,
                    threshold_ms=float(getattr(settings, "PERF_SLOW_REQUEST_MS", 3000)),
                    reason="avg_crawl_or_download_latency_high",
                )
            )

        if snap.avg_normalize_ms and snap.avg_normalize_ms > float(
            getattr(settings, "PERF_SLOW_NORMALIZE_MS", 500)
        ):
            out.append(
                BottleneckSignal(
                    stage="normalize",
                    store_name=st,
                    severity="high",
                    observed_ms=snap.avg_normalize_ms,
                    threshold_ms=float(getattr(settings, "PERF_SLOW_NORMALIZE_MS", 500)),
                    reason="avg_normalization_cost_high",
                )
            )

        if snap.avg_crm_send_ms and snap.avg_crm_send_ms > float(
            getattr(settings, "PERF_SLOW_CRM_SEND_MS", 2000)
        ):
            out.append(
                BottleneckSignal(
                    stage="crm_send",
                    store_name=st,
                    severity="high",
                    observed_ms=snap.avg_crm_send_ms,
                    threshold_ms=float(getattr(settings, "PERF_SLOW_CRM_SEND_MS", 2000)),
                    reason="avg_crm_http_send_latency_high",
                )
            )

        if snap.avg_batch_apply_ms and snap.avg_batch_apply_ms > float(
            getattr(settings, "PERF_SLOW_BATCH_APPLY_MS", 3000)
        ):
            out.append(
                BottleneckSignal(
                    stage="crm_apply_parse",
                    store_name=st,
                    severity="high",
                    observed_ms=snap.avg_batch_apply_ms,
                    threshold_ms=float(getattr(settings, "PERF_SLOW_BATCH_APPLY_MS", 3000)),
                    reason="avg_batch_response_parse_or_apply_path_slow",
                )
            )

        if (
            snap.products_per_minute is not None
            and snap.products_total >= 10
            and snap.products_per_minute < 2.0
        ):
            out.append(
                BottleneckSignal(
                    stage="product_parse",
                    store_name=st,
                    severity="warning",
                    observed_ms=snap.products_per_minute,
                    threshold_ms=2.0,
                    reason="low_products_per_minute_on_active_store",
                )
            )

    for stage, avg in run_snapshot.stage_averages_ms.items():
        if is_stage_slow(stage, avg, settings):
            sev: Literal["warning", "high"] = (
                "high"
                if avg > float(getattr(settings, "PERF_SLOW_CRM_SEND_MS", 2000)) * 2
                else "warning"
            )
            thr = threshold_ms_for_performance_stage(stage, settings)
            out.append(
                BottleneckSignal(
                    stage=cast_stage(stage),
                    store_name=None,
                    severity=sev,
                    observed_ms=avg,
                    threshold_ms=thr,
                    reason=f"run_level_avg_stage_slow:{stage}",
                )
            )

    return out


def cast_stage(stage: str) -> PerformanceStage:
    allowed: set[str] = {
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
    if stage in allowed:
        return cast(PerformanceStage, stage)
    return cast(PerformanceStage, "observability")


def threshold_ms_for_performance_stage(stage: str, settings: Any) -> float:
    if stage == "crawl_request":
        return float(getattr(settings, "PERF_SLOW_REQUEST_MS", 3000))
    if stage == "product_parse":
        return float(getattr(settings, "PERF_SLOW_PRODUCT_PARSE_MS", 1000))
    if stage == "normalize":
        return float(getattr(settings, "PERF_SLOW_NORMALIZE_MS", 500))
    if stage == "crm_send":
        return float(getattr(settings, "PERF_SLOW_CRM_SEND_MS", 2000))
    if stage in ("crm_apply_parse", "batch_buffer", "reconcile"):
        return float(getattr(settings, "PERF_SLOW_BATCH_APPLY_MS", 3000))
    return float(getattr(settings, "PERF_SLOW_CRM_SEND_MS", 2000))
