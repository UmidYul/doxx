from __future__ import annotations

from typing import Any

from domain.performance import BottleneckSignal, RunPerformanceSnapshot


def build_profiling_report(
    run_snapshot: RunPerformanceSnapshot,
    bottlenecks: list[BottleneckSignal],
) -> dict[str, Any]:
    slow_stores = sorted(
        run_snapshot.store_snapshots,
        key=lambda s: (s.avg_normalize_ms or 0.0)
        + (s.avg_crm_send_ms or 0.0)
        + (s.avg_request_ms or 0.0),
        reverse=True,
    )
    dominant = bottlenecks[0].reason if bottlenecks else "none_detected"
    recs = _recommendations(run_snapshot, bottlenecks)
    return {
        "kind": "profiling_report_v1",
        "run_id": run_snapshot.run_id,
        "slowest_stages": list(run_snapshot.slowest_stages),
        "slowest_stores": [s.store_name for s in slow_stores[:8]],
        "dominant_bottleneck": dominant,
        "stage_averages_ms": dict(run_snapshot.stage_averages_ms),
        "throughput": {
            s.store_name: {
                "products_per_minute": s.products_per_minute,
                "batches_per_minute": s.batches_per_minute,
            }
            for s in run_snapshot.store_snapshots
        },
        "resource": {
            s.store_name: s.memory_estimate_mb for s in run_snapshot.store_snapshots
        },
        "recommendations": recs,
        "bottleneck_count": len(bottlenecks),
    }


def _recommendations(
    run_snapshot: RunPerformanceSnapshot,
    bottlenecks: list[BottleneckSignal],
) -> list[str]:
    out: list[str] = []
    reasons = {b.reason for b in bottlenecks}
    stages = {b.stage for b in bottlenecks}
    if "avg_normalization_cost_high" in reasons or "normalize" in stages:
        out.append("normalization_dominates_review_spec_mapping_and_sanity_cost")
    if "avg_crm_http_send_latency_high" in reasons or "crm_send" in stages:
        out.append("crm_send_dominates_review_network_timeouts_and_batch_size")
    if "avg_batch_response_parse_or_apply_path_slow" in reasons or "crm_apply_parse" in stages:
        out.append("crm_apply_parse_dominates_review_response_shape_and_validation")
    if "avg_crawl_or_download_latency_high" in reasons or "crawl_request" in stages:
        out.append("crawl_request_dominates_review_store_access_mode_http_proxy_browser")
    if "low_products_per_minute_on_active_store" in reasons:
        out.append("throughput_dominates_review_listing_and_product_parse_stages")
    if any(b.severity == "critical" for b in bottlenecks):
        out.append("memory_or_slo_critical_review_process_budget_and_store_concurrency")
    if not out:
        out.append("no_dominant_bottleneck_in_threshold_model_collect_more_runs")
    return out


def build_human_profiling_report(
    run_snapshot: RunPerformanceSnapshot,
    bottlenecks: list[BottleneckSignal],
) -> str:
    data = build_profiling_report(run_snapshot, bottlenecks)
    lines = [
        f"Profiling report (run {data['run_id']})",
        f"Slowest stages: {', '.join(data['slowest_stages']) or 'n/a'}",
        f"Slowest stores: {', '.join(data['slowest_stores']) or 'n/a'}",
        f"Dominant bottleneck: {data['dominant_bottleneck']}",
        "",
        "Average stage latencies (ms):",
    ]
    for k, v in sorted(data["stage_averages_ms"].items(), key=lambda kv: kv[1], reverse=True):
        lines.append(f"  {k}: {v:.2f}")
    lines.append("")
    lines.append("Throughput (products/min per store):")
    for st, th in data["throughput"].items():
        lines.append(f"  {st}: {th.get('products_per_minute')}")
    lines.append("")
    lines.append("Resource (memory MB estimate per store snapshot):")
    for st, mb in data["resource"].items():
        lines.append(f"  {st}: {mb}")
    lines.append("")
    lines.append("Recommendations:")
    for r in data["recommendations"]:
        lines.append(f"  - {r}")
    return "\n".join(lines) + "\n"
