from __future__ import annotations

from domain.operational_policy import RunOperationalStatus, StoreOperationalStatus


def serialize_store_status(status: StoreOperationalStatus) -> dict[str, object]:
    """JSON-friendly store operational view (no raw trace buffers)."""
    return {
        "store_name": status.store_name,
        "status": status.status,
        "alerts": [a.model_dump(mode="json") for a in status.alerts],
        "breached_thresholds": [d.model_dump(mode="json") for d in status.breached_thresholds],
        "counters": dict(status.counters),
        "notes": list(status.notes),
    }


def serialize_run_status(status: RunOperationalStatus) -> dict[str, object]:
    """JSON-friendly run operational view for future REST/status export."""
    return {
        "run_id": status.run_id,
        "status": status.status,
        "store_statuses": [serialize_store_status(ss) for ss in status.store_statuses],
        "global_alerts": [a.model_dump(mode="json") for a in status.global_alerts],
        "notes": list(status.notes),
    }
