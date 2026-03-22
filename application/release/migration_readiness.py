from __future__ import annotations

from config.settings import settings
from domain.compatibility import CompatibilityReport, DeprecationNotice, MigrationPlan

from application.release import compatibility_logger as compat_log
from application.release.deprecation_registry import build_deprecation_warnings
from application.release.migration_planner import can_use_dual_shape, can_use_shadow_mode


def build_migration_readiness_report(
    reports: list[CompatibilityReport],
    plans: list[MigrationPlan],
    deprecations: list[DeprecationNotice],
) -> dict[str, object]:
    breaking_surfaces = [r.surface for r in reports if r.breaking_changes]
    safe_additive = [r.surface for r in reports if not r.breaking_changes and not r.conditional_changes]
    deprecated_in_use: list[str] = []
    for n in deprecations:
        if n.status in ("deprecated", "shadow"):
            deprecated_in_use.append(f"{n.surface}:{n.field_name}")

    dual_recommended = [r.surface for r in reports if can_use_dual_shape(r)]
    shadow_recommended = [r.surface for r in reports if can_use_shadow_mode(r)]

    allow_breaking = bool(getattr(settings, "ALLOW_BREAKING_CHANGES_WITHOUT_GATE", False))
    block = (not allow_breaking) and any(not r.compatible for r in reports)

    rollout_required = bool(breaking_surfaces or any(r.conditional_changes for r in reports))

    recommendation = "block_release" if block else ("staged_rollout" if rollout_required else "ship")

    rep: dict[str, object] = {
        "surfaces_with_breaking_changes": breaking_surfaces,
        "surfaces_safe_for_additive_release": safe_additive,
        "deprecated_fields_tracked": deprecated_in_use,
        "dual_shape_recommended_surfaces": dual_recommended,
        "shadow_mode_recommended_surfaces": shadow_recommended,
        "rollout_required": rollout_required,
        "block_release_recommended": block,
        "release_recommendation": recommendation,
        "migration_plans": [p.model_dump() for p in plans],
        "compatibility_reports": [r.model_dump() for r in reports],
    }
    compat_log.emit_migration_readiness_reported(
        surface="*",
        from_version=getattr(settings, "CONTRACT_SCHEMA_VERSION", "v1"),
        to_version=getattr(settings, "CONTRACT_SCHEMA_VERSION", "v1"),
        recommended_action=recommendation,
    )
    return rep


def summarize_migration_risk(
    reports: list[CompatibilityReport],
    plans: list[MigrationPlan],
    deprecations: list[DeprecationNotice],
) -> str:
    doc = build_migration_readiness_report(reports, plans, deprecations)
    lines = [
        f"release_recommendation={doc['release_recommendation']}",
        f"block_release_recommended={doc['block_release_recommended']}",
        f"rollout_required={doc['rollout_required']}",
    ]
    if doc["surfaces_with_breaking_changes"]:
        lines.append("breaking:" + ",".join(str(x) for x in doc["surfaces_with_breaking_changes"]))
    if doc["dual_shape_recommended_surfaces"]:
        lines.append("dual_shape:" + ",".join(str(x) for x in doc["dual_shape_recommended_surfaces"]))
    if deprecations:
        lines.append(f"deprecations_tracked={len(deprecations)}")
    return "; ".join(lines)


def deprecated_fields_still_in_payloads(
    samples: dict[str, dict[str, object]],
) -> list[str]:
    """Detect deprecated field usage in sample payloads (surface -> payload)."""
    found: list[str] = []
    for surf, payload in samples.items():
        found.extend(build_deprecation_warnings(surf, payload))
    return found
