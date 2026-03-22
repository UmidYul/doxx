from __future__ import annotations

from typing import Any

from domain.cost_efficiency import EfficiencySignal, RunCostSnapshot, StoreCostSnapshot


def build_store_cost_payload(snapshot: StoreCostSnapshot) -> dict[str, Any]:
    return {
        "kind": "store_cost_v1",
        "store_name": snapshot.store_name,
        "estimated_cost_units": snapshot.estimated_cost_units,
        "status": snapshot.status,
        "products_per_cost_unit": snapshot.products_per_cost_unit,
        "applied_per_cost_unit": snapshot.applied_per_cost_unit,
        "mix": {
            "http": snapshot.http_requests,
            "proxy": snapshot.proxy_requests,
            "browser": snapshot.browser_pages,
            "retry": snapshot.retry_attempts,
        },
        "delivery": {
            "batch_flushes": snapshot.batch_flushes,
            "crm_roundtrips": snapshot.crm_roundtrips,
        },
        "yield": {
            "products_parsed": snapshot.products_parsed,
            "products_applied": snapshot.products_applied,
        },
    }


def build_run_cost_payload(snapshot: RunCostSnapshot) -> dict[str, Any]:
    return {
        "kind": "run_cost_v1",
        "run_id": snapshot.run_id,
        "total_estimated_cost_units": snapshot.total_estimated_cost_units,
        "overall_status": snapshot.overall_status,
        "highest_cost_stores": list(snapshot.highest_cost_stores),
        "lowest_efficiency_stores": list(snapshot.lowest_efficiency_stores),
        "stores": [build_store_cost_payload(s) for s in snapshot.store_snapshots],
    }


def build_efficiency_signal_payload(signals: list[EfficiencySignal]) -> dict[str, Any]:
    return {
        "kind": "efficiency_signals_v1",
        "count": len(signals),
        "items": [
            {
                "store_name": s.store_name,
                "severity": s.severity,
                "signal_code": s.signal_code,
                "observed_value": s.observed_value,
                "threshold_value": s.threshold_value,
                "reason": s.reason,
            }
            for s in signals
        ],
    }
