from __future__ import annotations

from config.settings import settings
from domain.observability import SyncCorrelationContext

from infrastructure.observability import message_codes as omc
from infrastructure.observability.event_logger import log_sync_event


def _corr(*, surface: str) -> SyncCorrelationContext:
    return SyncCorrelationContext(
        run_id="contract_compat",
        spider_name=f"compatibility:{surface}",
        store_name="*",
    )


def _emit(
    message_code: str,
    *,
    surface: str | None = None,
    change_name: str | None = None,
    compatibility_level: str | None = None,
    field_name: str | None = None,
    replacement_field: str | None = None,
    from_version: str | None = None,
    to_version: str | None = None,
    dual_shape_enabled: bool | None = None,
    shadow_enabled: bool | None = None,
    recommended_action: str | None = None,
    compatible: bool | None = None,
) -> None:
    if not settings.ENABLE_STRUCTURED_SYNC_LOGS and not settings.ENABLE_IN_MEMORY_TRACE_BUFFER:
        return
    details: dict[str, object] = {}
    if surface is not None:
        details["surface"] = surface
    if change_name is not None:
        details["change_name"] = change_name
    if compatibility_level is not None:
        details["compatibility_level"] = compatibility_level
    if field_name is not None:
        details["field_name"] = field_name
    if replacement_field is not None:
        details["replacement_field"] = replacement_field
    if from_version is not None:
        details["from_version"] = from_version
    if to_version is not None:
        details["to_version"] = to_version
    if dual_shape_enabled is not None:
        details["dual_shape_enabled"] = dual_shape_enabled
    if shadow_enabled is not None:
        details["shadow_enabled"] = shadow_enabled
    if recommended_action is not None:
        details["recommended_action"] = recommended_action
    if compatible is not None:
        details["compatible"] = compatible
    log_sync_event(
        "internal",
        "warning" if message_code in (omc.BREAKING_CHANGE_DETECTED, omc.COMPATIBILITY_GUARD_BLOCKED) else "info",
        message_code,
        _corr(surface=surface or "*"),
        details=details,
    )


def emit_compatibility_check_completed(*, surface: str, compatible: bool, compatibility_level: str) -> None:
    _emit(
        omc.COMPATIBILITY_CHECK_COMPLETED,
        surface=surface,
        compatible=compatible,
        compatibility_level=compatibility_level,
    )


def emit_breaking_change_detected(
    *,
    surface: str,
    change_name: str,
    compatibility_level: str,
    field_name: str | None,
    recommended_action: str,
) -> None:
    _emit(
        omc.BREAKING_CHANGE_DETECTED,
        surface=surface,
        change_name=change_name,
        compatibility_level=compatibility_level,
        field_name=field_name,
        recommended_action=recommended_action,
    )


def emit_deprecation_warning_emitted(
    *,
    surface: str,
    field_name: str | None,
    replacement_field: str | None,
    recommended_action: str,
) -> None:
    if not getattr(settings, "ENABLE_DEPRECATION_WARNINGS", True):
        return
    _emit(
        omc.DEPRECATION_WARNING_EMITTED,
        surface=surface,
        field_name=field_name,
        replacement_field=replacement_field,
        recommended_action=recommended_action,
    )


def emit_shadow_field_applied(
    *,
    surface: str,
    field_name: str,
    replacement_field: str,
    shadow_enabled: bool,
) -> None:
    _emit(
        omc.SHADOW_FIELD_APPLIED,
        surface=surface,
        field_name=field_name,
        replacement_field=replacement_field,
        shadow_enabled=shadow_enabled,
    )


def emit_dual_shape_output_built(
    *,
    surface: str,
    dual_shape_enabled: bool,
    shadow_enabled: bool,
    recommended_action: str,
) -> None:
    _emit(
        omc.DUAL_SHAPE_OUTPUT_BUILT,
        surface=surface,
        dual_shape_enabled=dual_shape_enabled,
        shadow_enabled=shadow_enabled,
        recommended_action=recommended_action,
    )


def emit_migration_plan_built(
    *,
    surface: str,
    from_version: str,
    to_version: str,
    recommended_action: str,
) -> None:
    _emit(
        omc.MIGRATION_PLAN_BUILT,
        surface=surface,
        from_version=from_version,
        to_version=to_version,
        recommended_action=recommended_action,
    )


def emit_migration_readiness_reported(
    *,
    surface: str,
    from_version: str,
    to_version: str,
    recommended_action: str,
) -> None:
    if not getattr(settings, "ENABLE_MIGRATION_READINESS_REPORT", True):
        return
    _emit(
        omc.MIGRATION_READINESS_REPORTED,
        surface=surface,
        from_version=from_version,
        to_version=to_version,
        recommended_action=recommended_action,
    )


def emit_compatibility_guard_blocked(
    *,
    surface: str,
    recommended_action: str,
    change_name: str | None = None,
) -> None:
    if not getattr(settings, "ENABLE_COMPATIBILITY_GUARDS", True):
        return
    _emit(
        omc.COMPATIBILITY_GUARD_BLOCKED,
        surface=surface,
        change_name=change_name,
        recommended_action=recommended_action,
    )
