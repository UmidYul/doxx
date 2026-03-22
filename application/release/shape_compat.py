from __future__ import annotations

import copy

from config.settings import settings

from application.release import compatibility_logger as compat_log
from application.release.deprecation_registry import get_deprecations, get_shadow_fields


def apply_shadow_fields(surface: str, payload: dict[str, object]) -> dict[str, object]:
    """Copy canonical values into legacy shadow keys when enabled (temporary migration aid)."""
    if not getattr(settings, "ENABLE_SHADOW_FIELDS", True):
        return payload
    out = dict(payload)
    mapping = get_shadow_fields(surface)
    for shadow_key, canonical in mapping.items():
        if canonical in out and shadow_key not in out:
            out[shadow_key] = copy.deepcopy(out[canonical])
            compat_log.emit_shadow_field_applied(
                surface=surface,
                field_name=shadow_key,
                replacement_field=canonical,
                shadow_enabled=True,
            )
    return out


def build_dual_shape_payload(surface: str, payload: dict[str, object]) -> dict[str, object]:
    """
    When dual-shape is enabled, nest primary payload and duplicate legacy+canonical field sets.
    Not enabled by default — avoids permanent dual-write.
    """
    if not getattr(settings, "ENABLE_DUAL_SHAPE_OUTPUTS", False):
        return dict(payload)
    primary = apply_shadow_fields(surface, dict(payload))
    legacy = dict(primary)
    mapping = get_shadow_fields(surface)
    for shadow_key, canonical in mapping.items():
        if canonical in primary:
            legacy[shadow_key] = copy.deepcopy(primary[canonical])
        if shadow_key in primary and canonical not in primary:
            legacy[canonical] = copy.deepcopy(primary[shadow_key])
    dual: dict[str, object] = {
        "contract_schema_version": getattr(settings, "CONTRACT_SCHEMA_VERSION", "v1"),
        "primary": primary,
        "legacy_shape": legacy,
    }
    compat_log.emit_dual_shape_output_built(
        surface=surface,
        dual_shape_enabled=True,
        shadow_enabled=bool(getattr(settings, "ENABLE_SHADOW_FIELDS", True)),
        recommended_action="consume_primary_then_migrate_off_legacy",
    )
    return dual


def strip_removed_fields(surface: str, payload: dict[str, object]) -> dict[str, object]:
    """Remove fields marked ``removed`` in deprecation registry (post gate / migration)."""
    if not getattr(settings, "ENABLE_COMPATIBILITY_GUARDS", True):
        return payload
    out = dict(payload)
    for n in get_deprecations(surface):
        if n.status != "removed":
            continue
        if n.field_name in out:
            out.pop(n.field_name, None)
    return out


def apply_export_compatibility(surface: str, payload: dict[str, object]) -> dict[str, object]:
    """
    Pipeline for outbound dicts: strip removed → shadow → deprecation warnings → optional dual-shape.
    """
    out = strip_removed_fields(surface, dict(payload))
    if getattr(settings, "ENABLE_SHADOW_FIELDS", True):
        out = apply_shadow_fields(surface, out)
    if getattr(settings, "ENABLE_DEPRECATION_WARNINGS", True):
        for n in get_deprecations(surface):
            if n.status not in ("deprecated", "shadow"):
                continue
            if n.field_name in out:
                compat_log.emit_deprecation_warning_emitted(
                    surface=surface,
                    field_name=n.field_name,
                    replacement_field=n.replacement_field,
                    recommended_action="migrate_to_replacement_field",
                )
    if getattr(settings, "ENABLE_DUAL_SHAPE_OUTPUTS", False):
        out = build_dual_shape_payload(surface, out)
    return out
