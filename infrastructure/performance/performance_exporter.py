from __future__ import annotations

from typing import Any

from domain.performance import BottleneckSignal, RunPerformanceSnapshot, StorePerformanceSnapshot


def build_store_performance_payload(store_snapshot: StorePerformanceSnapshot) -> dict[str, Any]:
    return {
        "kind": "store_performance_v1",
        "store_name": store_snapshot.store_name,
        "requests_total": store_snapshot.requests_total,
        "products_total": store_snapshot.products_total,
        "batches_total": store_snapshot.batches_total,
        "avg_request_ms": store_snapshot.avg_request_ms,
        "avg_product_parse_ms": store_snapshot.avg_product_parse_ms,
        "avg_normalize_ms": store_snapshot.avg_normalize_ms,
        "avg_crm_send_ms": store_snapshot.avg_crm_send_ms,
        "avg_batch_apply_ms": store_snapshot.avg_batch_apply_ms,
        "products_per_minute": store_snapshot.products_per_minute,
        "batches_per_minute": store_snapshot.batches_per_minute,
        "memory_estimate_mb": store_snapshot.memory_estimate_mb,
        "status": store_snapshot.status,
    }


def build_run_performance_payload(run_snapshot: RunPerformanceSnapshot) -> dict[str, Any]:
    return {
        "kind": "run_performance_v1",
        "run_id": run_snapshot.run_id,
        "started_at": run_snapshot.started_at.isoformat(),
        "stores": list(run_snapshot.stores),
        "stage_averages_ms": dict(run_snapshot.stage_averages_ms),
        "slowest_stages": list(run_snapshot.slowest_stages),
        "bottleneck_codes": list(run_snapshot.bottlenecks),
        "overall_status": run_snapshot.overall_status,
        "store_summaries": [
            build_store_performance_payload(s) for s in run_snapshot.store_snapshots
        ],
    }


def build_bottleneck_summary(signals: list[BottleneckSignal]) -> dict[str, Any]:
    by_stage: dict[str, int] = {}
    by_sev: dict[str, int] = {}
    for s in signals:
        by_stage[s.stage] = by_stage.get(s.stage, 0) + 1
        by_sev[s.severity] = by_sev.get(s.severity, 0) + 1
    top = sorted(signals, key=lambda x: x.observed_ms, reverse=True)[:12]
    return {
        "kind": "bottleneck_summary_v1",
        "total_signals": len(signals),
        "counts_by_stage": by_stage,
        "counts_by_severity": by_sev,
        "top_signals": [
            {
                "stage": t.stage,
                "store_name": t.store_name,
                "severity": t.severity,
                "observed_ms": t.observed_ms,
                "threshold_ms": t.threshold_ms,
                "reason": t.reason,
            }
            for t in top
        ],
    }
