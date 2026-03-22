from __future__ import annotations

from typing import cast

from config.settings import settings
from domain.compatibility import CompatibilityLevel, CompatibilityReport, ContractChange, ContractSurface

from application.release import compatibility_logger as compat_log
from application.release.contract_evolution import classify_contract_change

_CORE_SURFACES: tuple[str, ...] = (
    "crm_payload",
    "lifecycle_event",
    "apply_result",
    "etl_status",
    "diagnostic_snapshot",
)


def _aggregate_level(changes: list[ContractChange]) -> CompatibilityLevel:
    if any(c.compatibility_level == "breaking" for c in changes):
        return "breaking"
    if any(c.compatibility_level == "conditionally_compatible" for c in changes):
        return "conditionally_compatible"
    return "backward_compatible"


def check_surface_compatibility(
    surface: str,
    baseline: dict[str, object],
    current: dict[str, object],
) -> CompatibilityReport:
    changes = classify_contract_change(surface, baseline, current)
    breaking = [c for c in changes if c.compatibility_level == "breaking"]
    conditional = [c for c in changes if c.compatibility_level == "conditionally_compatible"]
    additive = [c for c in changes if c.change_type == "additive"]

    level = _aggregate_level(changes)
    allow_breaking = bool(getattr(settings, "ALLOW_BREAKING_CHANGES_WITHOUT_GATE", False))
    compatible = len(breaking) == 0 or allow_breaking

    notes: list[str] = []
    if breaking and not allow_breaking:
        notes.append("Breaking changes detected; blocked unless ALLOW_BREAKING_CHANGES_WITHOUT_GATE=true.")
    if conditional:
        notes.append("Conditional compatibility: coordinate with CRM before relying on new shape.")

    report = CompatibilityReport(
        surface=cast(ContractSurface, surface),
        compatible=compatible,
        compatibility_level=level if compatible or allow_breaking else "breaking",
        breaking_changes=breaking,
        conditional_changes=conditional,
        additive_changes=additive,
        notes=notes,
    )
    compat_log.emit_compatibility_check_completed(
        surface=surface,
        compatible=compatible,
        compatibility_level=report.compatibility_level,
    )
    for c in breaking:
        compat_log.emit_breaking_change_detected(
            surface=surface,
            change_name=c.change_name,
            compatibility_level=c.compatibility_level,
            field_name=c.affected_fields[0] if c.affected_fields else None,
            recommended_action="dual_shape_or_shadow_or_gate",
        )
    return report


def check_all_core_surfaces(fixtures: dict[str, tuple[dict, dict]]) -> list[CompatibilityReport]:
    """fixtures: surface -> (baseline_dict, current_dict)."""
    reports: list[CompatibilityReport] = []
    for s in _CORE_SURFACES:
        pair = fixtures.get(s)
        if pair is None:
            continue
        base, cur = pair
        reports.append(check_surface_compatibility(s, dict(base), dict(cur)))
    return reports


def should_block_due_to_compatibility(reports: list[CompatibilityReport]) -> bool:
    if getattr(settings, "ALLOW_BREAKING_CHANGES_WITHOUT_GATE", False):
        return False
    return any(not r.compatible for r in reports)
