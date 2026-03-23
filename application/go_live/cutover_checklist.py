from __future__ import annotations

from config.settings import settings
from domain.go_live import CutoverChecklistItem
from domain.implementation_roadmap import ImplementationRoadmap
from domain.production_readiness import ProductionReadinessReport


def build_cutover_checklist(
    readiness_report: ProductionReadinessReport,
    roadmap: ImplementationRoadmap | None,
    rollout_summary: dict[str, object] | None,
    *,
    statuses: dict[str, object] | None = None,
) -> list[CutoverChecklistItem]:
    """Operational cutover checklist derived from readiness, rollout snapshot, and explicit statuses."""
    if not getattr(settings, "ENABLE_CUTOVER_CHECKLIST", True):
        return []

    st = statuses or {}

    def _b(key: str, default: bool = False) -> bool:
        v = st.get(key)
        return v if isinstance(v, bool) else default

    rs = rollout_summary or {}
    stores_by_stage = rs.get("stores_by_stage") or {}
    enabled = list(getattr(settings, "STORE_NAMES", []) or [])

    canary_ok = _b("canary_scope_confirmed", False)
    if getattr(settings, "GO_LIVE_CANARY_ONLY_FIRST", True) and enabled and rs:
        canary_stores = set(stores_by_stage.get("canary") or [])
        bad = set(stores_by_stage.get("full") or []) | set(stores_by_stage.get("partial") or [])
        violation = any(s in bad for s in enabled)
        all_on_canary = all(s in canary_stores for s in enabled)
        canary_ok = (all_on_canary and not violation) or _b("canary_exception_approved", False)

    roadmap_ok = True
    if roadmap is not None:
        blocker_codes = set(roadmap.go_live_blockers or [])
        if roadmap.critical_path and any(c in blocker_codes for c in roadmap.critical_path[:3]):
            roadmap_ok = not _b("roadmap_blockers_waived", False)

    items: list[CutoverChecklistItem] = [
        CutoverChecklistItem(
            item_code="cutover.production_config",
            title="Production config validated for target environment",
            completed=_b("production_config_validated", False),
            blocking=True,
            owner_role="platform",
            notes=[],
        ),
        CutoverChecklistItem(
            item_code="cutover.parser_key_security",
            title="Parser key / security config validated (secrets, signing mode)",
            completed=_b("parser_key_security_validated", False),
            blocking=True,
            owner_role="security",
            notes=[],
        ),
        CutoverChecklistItem(
            item_code="cutover.rollout_scope",
            title="Rollout scope confirmed against STORE_NAMES and CRM agreement",
            completed=_b("rollout_scope_confirmed", bool(rs)),
            blocking=True,
            owner_role="release_owner",
            notes=[],
        ),
        CutoverChecklistItem(
            item_code="cutover.enabled_stores",
            title="Enabled stores explicitly confirmed",
            completed=_b("enabled_stores_confirmed", len(enabled) > 0),
            blocking=True,
            owner_role="product_ops",
            notes=[f"stores={enabled}"],
        ),
        CutoverChecklistItem(
            item_code="cutover.canary_stage",
            title="Canary stage confirmed for first production launch",
            completed=canary_ok,
            blocking=getattr(settings, "GO_LIVE_CANARY_ONLY_FIRST", True),
            owner_role="release_owner",
            notes=[] if canary_ok else ["Store not exclusively on canary for first launch."],
        ),
        CutoverChecklistItem(
            item_code="cutover.support_docs",
            title="Support / triage docs available",
            completed=_b("support_triage_docs_available", readiness_report.overall_status in ("ready", "partial")),
            blocking=False,
            owner_role="support",
            notes=[],
        ),
        CutoverChecklistItem(
            item_code="cutover.rollback_advice",
            title="Rollback advisory path documented (deploy revert + store disable)",
            completed=_b("rollback_advisory_available", getattr(settings, "ENABLE_AUTO_ROLLBACK_ADVICE", True)),
            blocking=False,
            owner_role="release_owner",
            notes=[],
        ),
        CutoverChecklistItem(
            item_code="cutover.observability_export",
            title="Observability / status export available",
            completed=_b("observability_export_ok", getattr(settings, "ENABLE_ETL_STATUS_EXPORT", True)),
            blocking=True,
            owner_role="platform",
            notes=[],
        ),
        CutoverChecklistItem(
            item_code="cutover.dry_run_smoke",
            title="Dry-run and smoke completed",
            completed=_b("dry_run_passed", False) and _b("smoke_passed", False),
            blocking=True,
            owner_role="qa",
            notes=[],
        ),
        CutoverChecklistItem(
            item_code="cutover.release_report_reviewed",
            title="Release report reviewed by owner",
            completed=_b("release_report_reviewed", False),
            blocking=True,
            owner_role="release_owner",
            notes=[],
        ),
    ]

    items.append(
        CutoverChecklistItem(
            item_code="cutover.roadmap_canary_readiness",
            title="Roadmap shows no unresolved go-live blockers on critical path (10B)",
            completed=roadmap_ok,
            blocking=False,
            owner_role="engineering_lead",
            notes=[],
        )
    )

    return items


def evaluate_cutover_checklist(items: list[CutoverChecklistItem]) -> tuple[bool, list[str]]:
    blocking_open = [i.item_code for i in items if i.blocking and not i.completed]
    return (len(blocking_open) == 0, blocking_open)
