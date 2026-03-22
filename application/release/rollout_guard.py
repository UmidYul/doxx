from __future__ import annotations

from typing import Any

from config.settings import settings


def _status_str(obj: object | None, attr: str = "status") -> str | None:
    if obj is None:
        return None
    v = getattr(obj, attr, None)
    return str(v).lower() if v is not None else None


def should_block_rollout_due_to_health(store_status: object | None = None, run_status: object | None = None) -> bool:
    if not settings.ENABLE_ROLLOUT_GUARD_BY_STATUS:
        return False
    if not settings.ROLLOUT_BLOCK_ON_FAILING_STATUS:
        return False
    for obj in (store_status, run_status):
        st = _status_str(obj)
        if st == "failing":
            return True
    return False


def can_enable_feature_based_on_status(
    feature_name: str,
    store_status: object | None = None,
    run_status: object | None = None,
) -> bool:
    """Advisory guard: block aggressive features when health is bad."""
    if not settings.ENABLE_ROLLOUT_GUARD_BY_STATUS:
        return True
    if should_block_rollout_due_to_health(store_status, run_status):
        return False
    st = _status_str(store_status)
    ru = _status_str(run_status)
    if st == "degraded" or ru == "degraded":
        if feature_name in ("lifecycle_delta_events", "replay_reconciliation", "browser_escalation_policy"):
            if not settings.ROLLOUT_ALLOW_DEGRADED_CANARY:
                return False
    return True


def can_promote_stage(current_stage: str, store_status: object | None = None) -> bool:
    _ = current_stage
    if not settings.ENABLE_ROLLOUT_GUARD_BY_STATUS:
        return True
    st = _status_str(store_status)
    if st in ("failing", "degraded"):
        return False
    return True
