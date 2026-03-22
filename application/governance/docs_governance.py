from __future__ import annotations

from pathlib import Path
from typing import Any

from config.settings import settings
from domain.project_ownership import KnowledgeAsset, ModuleOwnerRecord
from infrastructure.observability import message_codes as obs_mc
from infrastructure.observability.event_logger import log_knowledge_continuity_event

# Paths relative to repository root — knowledge continuity / release (9C).
_REQUIRED_DOC_RELPATHS: tuple[str, ...] = (
    "docs/README.md",
    "docs/onboarding.md",
    "OWNERSHIP_MAP.md",
    "docs/crm_integration.md",
    "docs/support_triage.md",
    "docs/release_process.md",
    "docs/fixtures_and_acceptance.md",
    "docs/store_playbook_template.md",
    "docs/adr/README.md",
    "docs/production_readiness.md",
)

_ADR_INDEX_MARKER = "docs/adr/README.md"


def list_required_docs() -> list[str]:
    """Canonical list of documentation assets required for gates and onboarding (9C)."""
    return list(_REQUIRED_DOC_RELPATHS)


def check_docs_presence(project_root: str) -> list[str]:
    """Return **missing** required doc paths (posix-style relative paths)."""
    root = Path(project_root)
    missing: list[str] = []
    for rel in list_required_docs():
        p = root / rel
        if not p.is_file():
            missing.append(rel.replace("\\", "/"))
    return missing


def _store_playbook_path(store: str) -> str:
    return f"docs/stores/{store.strip().lower()}.md"


def build_docs_coverage_report(
    project_root: str,
    *,
    store_names: list[str] | None = None,
    emit_structured_logs: bool = False,
) -> dict[str, Any]:
    """Summarize documentation presence, per-store playbooks, and coverage percentage."""
    root = Path(project_root)
    stores = [s.strip() for s in (store_names or list(settings.STORE_NAMES)) if s.strip()]
    required = list_required_docs()
    missing_required = check_docs_presence(project_root)

    store_status: dict[str, bool] = {}
    missing_playbooks: list[str] = []
    for st in stores:
        rel = _store_playbook_path(st)
        ok = (root / rel).is_file()
        store_status[st] = ok
        if not ok:
            missing_playbooks.append(rel)
            if emit_structured_logs:
                log_knowledge_continuity_event(
                    obs_mc.STORE_PLAYBOOK_MISSING,
                    store_name=st,
                    missing_doc=rel,
                    path=rel,
                    risk_level="high",
                )

    total_units = len(required) + len(stores)
    present = sum(1 for r in required if (root / r).is_file()) + sum(1 for v in store_status.values() if v)
    coverage_pct = round(100.0 * present / total_units, 2) if total_units else 100.0

    critical_docs_missing = list(missing_required)
    critical_gaps: list[str] = []
    for m in critical_docs_missing:
        critical_gaps.append(f"missing_required_doc:{m}")
    for m in missing_playbooks:
        critical_gaps.append(f"missing_store_playbook:{m}")

    report: dict[str, Any] = {
        "required_doc_paths": [r.replace("\\", "/") for r in required],
        "present_required_count": len(required) - len(missing_required),
        "total_required_docs": len(required),
        "store_playbooks": store_status,
        "stores_missing_playbooks": missing_playbooks,
        "coverage_pct": coverage_pct,
        "missing_required_docs": [m.replace("\\", "/") for m in missing_required],
        "critical_docs_missing": critical_docs_missing,
        "critical_gaps": critical_gaps,
        "adr_index_ok": (root / _ADR_INDEX_MARKER).is_file(),
    }

    if emit_structured_logs:
        log_knowledge_continuity_event(
            obs_mc.DOCS_COVERAGE_CHECK_COMPLETED,
            coverage_pct=coverage_pct,
            path=str(root),
            details={"missing_count": len(missing_required) + len(missing_playbooks), "report": report},
        )

    return report


def compute_docs_governance_flags(
    project_root: str,
    *,
    store_names: list[str] | None = None,
    min_coverage_pct: float = 95.0,
    emit_structured_logs: bool = False,
) -> dict[str, bool]:
    """Booleans for :func:`application.release.release_gate_evaluator.evaluate_release_gates` (9C)."""
    report = build_docs_coverage_report(
        project_root,
        store_names=store_names,
        emit_structured_logs=emit_structured_logs,
    )
    missing_req = report["missing_required_docs"]
    missing_pb = report["stores_missing_playbooks"]
    cov = float(report["coverage_pct"])

    bundle_ok = (
        len(missing_req) == 0
        and (Path(project_root) / "docs/crm_integration.md").is_file()
        and (Path(project_root) / "docs/support_triage.md").is_file()
        and (Path(project_root) / "docs/release_process.md").is_file()
    )

    docs_required_present = len(missing_req) == 0
    store_playbooks_for_enabled_stores = len(missing_pb) == 0
    crm_integration_release_support_docs_present = bundle_ok
    docs_coverage_acceptable = cov >= min_coverage_pct and docs_required_present and store_playbooks_for_enabled_stores

    critical = bool(missing_req or missing_pb)
    knowledge_continuity_no_critical_gaps = not critical and cov >= min_coverage_pct

    if emit_structured_logs and not (docs_required_present and store_playbooks_for_enabled_stores):
        log_knowledge_continuity_event(
            obs_mc.DOCS_GOVERNANCE_GATE_FAILED,
            coverage_pct=cov,
            risk_level="high" if critical else "medium",
            details={"missing_required": missing_req, "missing_playbooks": missing_pb},
        )

    return {
        "docs_required_present": docs_required_present,
        "store_playbooks_for_enabled_stores": store_playbooks_for_enabled_stores,
        "crm_integration_release_support_docs_present": crm_integration_release_support_docs_present,
        "docs_coverage_acceptable": docs_coverage_acceptable,
        "knowledge_continuity_no_critical_gaps": knowledge_continuity_no_critical_gaps,
    }


def default_knowledge_assets() -> list[KnowledgeAsset]:
    """Reference catalog for continuity tooling (paths must exist in repo)."""
    return [
        KnowledgeAsset(
            asset_name="Docs index",
            asset_type="doc",
            path="docs/README.md",
            purpose="Navigation entry for all documentation.",
        ),
        KnowledgeAsset(
            asset_name="Ownership map",
            asset_type="doc",
            path="OWNERSHIP_MAP.md",
            purpose="Areas, escalation, change-sensitive zones.",
        ),
        KnowledgeAsset(
            asset_name="ADR index",
            asset_type="adr",
            path="docs/adr/README.md",
            purpose="Architecture decision records index.",
        ),
    ]


def minimal_ownership_registry_for_ci() -> list[ModuleOwnerRecord]:
    """Covers expected areas so continuity checks can pass when using code registry."""
    return [
        ModuleOwnerRecord(
            ownership_area="store_spiders",
            primary_owner_role="parser_team",
            modules=["infrastructure/spiders"],
        ),
        ModuleOwnerRecord(
            ownership_area="normalization",
            primary_owner_role="parser_team",
            modules=["infrastructure/pipelines/normalize_pipeline.py", "application/extractors"],
        ),
        ModuleOwnerRecord(
            ownership_area="lifecycle_crm",
            primary_owner_role="integrations",
            modules=["application/lifecycle"],
        ),
        ModuleOwnerRecord(
            ownership_area="transport_sync",
            primary_owner_role="integrations",
            modules=["infrastructure/transports", "infrastructure/pipelines/sync_pipeline.py"],
        ),
        ModuleOwnerRecord(
            ownership_area="observability_support",
            primary_owner_role="platform",
            modules=["infrastructure/observability"],
        ),
        ModuleOwnerRecord(
            ownership_area="security",
            primary_owner_role="security",
            modules=["infrastructure/security"],
        ),
        ModuleOwnerRecord(
            ownership_area="performance_rollout_release",
            primary_owner_role="release_owner",
            modules=["application/release", "application/governance"],
        ),
        ModuleOwnerRecord(
            ownership_area="docs_fixtures_acceptance",
            primary_owner_role="parser_team",
            modules=["docs", "tests/fixtures"],
        ),
    ]
