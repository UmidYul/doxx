from __future__ import annotations

from config.settings import settings
from infrastructure.observability import message_codes as omc


def _emit(code: str, details: dict[str, object]) -> None:
    if not getattr(settings, "ENABLE_STRUCTURED_SYNC_LOGS", True):
        return
    from infrastructure.observability.operational_logger import emit_operational_event

    emit_operational_event(code, run_id="rollout_policy", details=details)


def log_feature_rollout_decided(
    *,
    feature_name: str,
    store_name: str | None,
    stage: str,
    enabled: bool,
    canary_selected: bool,
    rollout_percentage: int | None,
    reason: str | None,
    rollout_scope: str,
) -> None:
    _emit(
        omc.FEATURE_ROLLOUT_DECIDED,
        {
            "feature_name": feature_name,
            "store_name": store_name,
            "stage": stage,
            "enabled": enabled,
            "canary_selected": canary_selected,
            "rollout_percentage": rollout_percentage,
            "reason": reason,
            "rollout_scope": rollout_scope,
        },
    )


def log_store_rollout_decided(*, store_name: str, stage: str, enabled: bool, canary: bool, reason: str | None) -> None:
    _emit(
        omc.STORE_ROLLOUT_DECIDED,
        {
            "store_name": store_name,
            "stage": stage,
            "enabled": enabled,
            "canary": canary,
            "reason": reason,
        },
    )


def log_canary_bucket_selected(*, key: str, percentage: int, selected: bool) -> None:
    _emit(
        omc.CANARY_BUCKET_SELECTED,
        {
            "rollout_key": key,
            "rollout_percentage": percentage,
            "canary_selected": selected,
        },
    )


def log_rollout_guard_blocked(*, feature_name: str, store_name: str | None, reason: str, status: str | None) -> None:
    _emit(
        omc.ROLLOUT_GUARD_BLOCKED,
        {
            "feature_name": feature_name,
            "store_name": store_name,
            "reason": reason,
            "status": status,
        },
    )


def log_stage_promotion_suggested(*, from_stage: str, to_stage: str, store_name: str | None, reason: str) -> None:
    _emit(
        omc.ROLLOUT_STAGE_PROMOTION_SUGGESTED,
        {
            "from_stage": from_stage,
            "to_stage": to_stage,
            "store_name": store_name,
            "reason": reason,
        },
    )


def log_rollback_advice_emitted(*, scope: str, target: str | None, reason: str, recommended_stage: str) -> None:
    _emit(
        omc.ROLLBACK_ADVICE_EMITTED,
        {
            "rollback_scope": scope,
            "target_name": target,
            "reason": reason,
            "recommended_stage": recommended_stage,
        },
    )


def log_store_enablement_decided(*, store_name: str, allowed: bool, stage: str, reason: str | None) -> None:
    _emit(
        omc.STORE_ENABLEMENT_DECIDED,
        {
            "store_name": store_name,
            "enabled": allowed,
            "stage": stage,
            "reason": reason,
        },
    )
