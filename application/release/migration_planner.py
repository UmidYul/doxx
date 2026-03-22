from __future__ import annotations

from domain.compatibility import CompatibilityReport, MigrationPlan

from application.release import compatibility_logger as compat_log


def can_use_dual_shape(report: CompatibilityReport) -> bool:
    """Dual-shape helps when breaking or conditional field renames/removals are present."""
    return bool(report.breaking_changes or report.conditional_changes)


def can_use_shadow_mode(report: CompatibilityReport) -> bool:
    """Shadow mode recommended for conditional/breaking field transitions."""
    return bool(report.breaking_changes or report.conditional_changes or report.compatibility_level != "backward_compatible")


def build_migration_plan(
    surface: str,
    from_version: str,
    to_version: str,
    compatibility_report: CompatibilityReport,
) -> MigrationPlan:
    steps: list[str] = []
    notes: list[str] = list(compatibility_report.notes)
    dual = can_use_dual_shape(compatibility_report)
    shadow = can_use_shadow_mode(compatibility_report)

    if not compatibility_report.breaking_changes and not compatibility_report.conditional_changes:
        steps.append("No hard migration: additive-only or identical shape.")
        notes.append("Safe for standard rollout.")
        return MigrationPlan(
            surface=compatibility_report.surface,
            from_version=from_version,
            to_version=to_version,
            required_steps=steps,
            can_dual_write=False,
            can_shadow_mode=False,
            rollback_possible=True,
            notes=notes,
        )

    if compatibility_report.breaking_changes:
        steps.append("Stage 1: announce breaking changes to CRM/downstream owners.")
        steps.append("Stage 2: enable shadow fields or dual-shape exports during transition.")
        steps.append("Stage 3: verify migration readiness report is green in CI/release gate.")
        notes.append("Breaking changes require explicit gate approval or dual-shape period.")

    all_changes = (
        compatibility_report.breaking_changes
        + compatibility_report.conditional_changes
        + compatibility_report.additive_changes
    )
    if any(c.change_type == "behavioral" for c in all_changes):
        steps.append("Behavioral lifecycle change: use staged rollout (canary / partial stores) only.")
        notes.append("Avoid big-bang for semantic lifecycle shifts.")

    if surface in ("etl_status", "diagnostic_snapshot"):
        steps.append("Prefer backward-compatible observability keys; keep deprecated keys until CRM confirms.")
        notes.append("Observability/export surfaces favor additive evolution.")

    rollback = not any(c.change_type == "breaking" for c in compatibility_report.breaking_changes) or dual

    plan = MigrationPlan(
        surface=compatibility_report.surface,
        from_version=from_version,
        to_version=to_version,
        required_steps=steps,
        can_dual_write=dual,
        can_shadow_mode=shadow,
        rollback_possible=rollback,
        notes=notes,
    )
    compat_log.emit_migration_plan_built(
        surface=surface,
        from_version=from_version,
        to_version=to_version,
        recommended_action="follow_required_steps",
    )
    return plan


def explain_migration_steps(plan: MigrationPlan) -> list[str]:
    lines: list[str] = [
        f"Surface={plan.surface} {plan.from_version}→{plan.to_version}",
        f"dual_write_recommended={plan.can_dual_write}",
        f"shadow_mode_recommended={plan.can_shadow_mode}",
        f"rollback_possible={plan.rollback_possible}",
    ]
    lines.extend(plan.required_steps)
    if plan.notes:
        lines.append("Notes:")
        lines.extend(f"- {n}" for n in plan.notes)
    return lines
