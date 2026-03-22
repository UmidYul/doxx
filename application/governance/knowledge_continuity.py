from __future__ import annotations

from pathlib import Path
from typing import Any

from domain.project_ownership import KnowledgeAsset, ModuleOwnerRecord
from infrastructure.observability import message_codes as obs_mc
from infrastructure.observability.event_logger import log_knowledge_continuity_event

# Expected logical ownership areas (9C) — should align with OWNERSHIP_MAP.md sections.
EXPECTED_OWNERSHIP_AREA_KEYS: frozenset[str] = frozenset(
    {
        "store_spiders",
        "normalization",
        "lifecycle_crm",
        "transport_sync",
        "observability_support",
        "security",
        "performance_rollout_release",
        "docs_fixtures_acceptance",
    }
)

# Critical path prefixes that should appear in at least one ModuleOwnerRecord.modules entry.
_CRITICAL_MODULE_PREFIXES: tuple[str, ...] = (
    "infrastructure/spiders",
    "infrastructure/pipelines/normalize_pipeline.py",
    "application/lifecycle",
    "infrastructure/transports",
    "infrastructure/pipelines/sync_pipeline.py",
    "infrastructure/observability",
    "infrastructure/security",
    "application/release",
    "docs",
)


def _module_prefix_covered(prefix: str, records: list[ModuleOwnerRecord]) -> bool:
    for r in records:
        for m in r.modules:
            if m == prefix or m.startswith(prefix.rstrip("/") + "/") or prefix.startswith(m.rstrip("/")):
                return True
            if prefix in m or m in prefix:
                return True
    return False


def recommend_missing_docs(docs_coverage: dict[str, Any], *, store_names: list[str]) -> list[str]:
    """Actionable list of missing documentation assets."""
    out: list[str] = []
    for m in docs_coverage.get("missing_required_docs") or []:
        out.append(f"add_or_restore:{m}")
    missing_pb = [x.replace("\\", "/") for x in (docs_coverage.get("stores_missing_playbooks") or [])]
    for st in store_names:
        rel = f"docs/stores/{st.strip().lower()}.md"
        if rel in missing_pb:
            out.append(f"create_store_playbook:{rel}")
    return out


def summarize_knowledge_risk(report: dict[str, Any]) -> str:
    """One-line human summary for logs and CI."""
    lvl = str(report.get("risk_level") or "unknown")
    n_missing = len(report.get("missing_key_docs") or [])
    n_stores = len(report.get("stores_without_playbooks") or [])
    n_uncovered = len(report.get("uncovered_ownership_areas") or [])
    return (
        f"risk_level={lvl}; missing_docs={n_missing}; stores_without_playbook={n_stores}; "
        f"uncovered_ownership_areas={n_uncovered}"
    )


def build_knowledge_continuity_report(
    ownership_records: list[ModuleOwnerRecord] | None,
    knowledge_assets: list[KnowledgeAsset],
    docs_coverage: dict[str, Any],
    *,
    emit_structured_logs: bool = False,
) -> dict[str, Any]:
    """Merge docs coverage with optional code ownership registry (9C)."""
    records = ownership_records or []
    covered_areas = {r.ownership_area for r in records}
    if records:
        uncovered = sorted(EXPECTED_OWNERSHIP_AREA_KEYS - covered_areas)
    else:
        uncovered = sorted(EXPECTED_OWNERSHIP_AREA_KEYS)

    missing_docs = list(docs_coverage.get("missing_required_docs") or [])
    sp = docs_coverage.get("store_playbooks")
    if isinstance(sp, dict) and sp:
        stores_wo = [k for k, v in sp.items() if not v]
    else:
        stores_wo = [Path(str(p)).stem for p in docs_coverage.get("stores_missing_playbooks") or []]

    modules_wo: list[str] = []
    if records:
        for pref in _CRITICAL_MODULE_PREFIXES:
            if not _module_prefix_covered(pref, records):
                modules_wo.append(pref)

    risk_level = "low"
    critical_gaps: list[str] = list(docs_coverage.get("critical_gaps") or [])
    if missing_docs or stores_wo:
        risk_level = "high"
    elif modules_wo:
        risk_level = "medium"
    elif uncovered and records:
        risk_level = "medium"
    elif not records and uncovered:
        risk_level = "medium"
    elif float(docs_coverage.get("coverage_pct") or 0) < 95.0:
        risk_level = "medium"

    summary = summarize_knowledge_risk(
        {
            "risk_level": risk_level,
            "missing_key_docs": missing_docs,
            "stores_without_playbooks": stores_wo,
            "uncovered_ownership_areas": uncovered,
        }
    )

    out: dict[str, Any] = {
        "uncovered_ownership_areas": uncovered,
        "missing_key_docs": missing_docs,
        "stores_without_playbooks": stores_wo,
        "modules_without_obvious_ownership_area": modules_wo,
        "supportability_risk_summary": summary,
        "risk_level": risk_level,
        "critical_gaps": critical_gaps,
        "coverage_pct": docs_coverage.get("coverage_pct"),
        "ownership_registry_empty": len(records) == 0,
        "knowledge_assets_count": len(knowledge_assets),
    }

    if emit_structured_logs:
        log_knowledge_continuity_event(
            obs_mc.KNOWLEDGE_CONTINUITY_REPORT_BUILT,
            coverage_pct=float(docs_coverage.get("coverage_pct") or 0),
            risk_level=risk_level,
            details=out,
        )
        log_knowledge_continuity_event(
            obs_mc.OWNERSHIP_MAP_BUILT,
            ownership_area="*",
            details={"areas_covered": sorted(covered_areas), "uncovered": uncovered},
        )

    return out
