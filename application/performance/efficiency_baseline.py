from __future__ import annotations

import json
from pathlib import Path
from domain.cost_efficiency import RunCostSnapshot
from domain.performance import RunPerformanceSnapshot


def build_efficiency_baseline_from_snapshot(
    run_snapshot: RunPerformanceSnapshot,
    cost_snapshot: RunCostSnapshot,
) -> dict[str, float]:
    """Flatten perf + cost snapshots into a simple numeric baseline dict."""
    out: dict[str, float] = {}
    ss = run_snapshot.store_snapshots
    if ss:
        ar = [s.avg_request_ms for s in ss if s.avg_request_ms is not None]
        if ar:
            out["avg_request_ms"] = sum(ar) / float(len(ar))
        an = [s.avg_normalize_ms for s in ss if s.avg_normalize_ms is not None]
        if an:
            out["avg_normalize_ms"] = sum(an) / float(len(an))
        ac = [s.avg_crm_send_ms for s in ss if s.avg_crm_send_ms is not None]
        if ac:
            out["avg_crm_send_ms"] = sum(ac) / float(len(ac))
        pm = [s.products_per_minute for s in ss if s.products_per_minute is not None]
        if pm:
            out["products_per_minute"] = sum(pm) / float(len(pm))

    total_cost = cost_snapshot.total_estimated_cost_units
    parsed = sum(s.products_parsed for s in cost_snapshot.store_snapshots)
    applied = sum(s.products_applied for s in cost_snapshot.store_snapshots)
    if parsed > 0 and total_cost > 0:
        out["cost_per_product"] = total_cost / float(parsed)
    if applied > 0 and total_cost > 0:
        out["cost_per_applied_item"] = total_cost / float(applied)

    return out


def load_efficiency_baseline(path: str) -> dict[str, float]:
    p = Path(path)
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    return {str(k): float(v) for k, v in raw.items() if isinstance(v, (int, float))}


def save_efficiency_baseline(path: str, baseline: dict[str, float]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(baseline, indent=2, sort_keys=True), encoding="utf-8")
