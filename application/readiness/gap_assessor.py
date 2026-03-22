from __future__ import annotations

from pathlib import Path

from config.settings import settings
from domain.production_readiness import (
    ReadinessChecklistItem,
    ReadinessEvidence,
    ReadinessGap,
    ReadinessStatus,
)

# item_code -> relative paths; **all** must exist for "ready".
_ITEM_PATHS_READY: dict[str, list[str]] = {
    "crawl.traversal_framework": ["infrastructure/spiders/base.py"],
    "crawl.duplicate_protection": ["infrastructure/pipelines/sync_pipeline.py"],
    "crawl.pagination_safety": ["config/settings.py"],
    "crawl.store_acceptance": ["tests/regression/test_normalization_regression.py"],
    "norm.hybrid_payload": ["domain/normalized_product.py"],
    "norm.typed_mapping": ["application/extractors/spec_mapper.py"],
    "norm.confidence_suppression": ["application/extractors/spec_sanity.py"],
    "norm.low_coverage_detection": ["infrastructure/pipelines/normalize_pipeline.py"],
    "crm.transport": ["infrastructure/transports/crm_http.py"],
    "crm.auth": ["infrastructure/security/secret_loader.py"],
    "crm.payload_contract": ["tests/contracts/test_crm_payload_contract.py"],
    "life.product_found_default": ["application/lifecycle/lifecycle_policy.py"],
    "life.fallback_policy": ["application/lifecycle/delta_downgrade.py"],
    "life.lifecycle_tests": ["tests/unit/test_lifecycle_builder.py"],
    "batch.partial_success": ["infrastructure/pipelines/sync_pipeline.py"],
    "batch.retryable": ["infrastructure/transports/crm_http.py"],
    "batch.duplicate_skip": ["infrastructure/pipelines/sync_pipeline.py"],
    "replay.idempotency_key": ["application/lifecycle/idempotency.py"],
    "replay.replay_safe_product_found": ["application/lifecycle/replay_policy.py"],
    "replay.reconciliation": ["application/lifecycle/reconciliation.py"],
    "obs.structured_traces": ["infrastructure/observability/event_logger.py"],
    "obs.batch_traces": ["infrastructure/observability/trace_collector.py"],
    "obs.etl_export": ["infrastructure/observability/etl_status_exporter.py"],
    "obs.failure_classification": ["infrastructure/observability/failure_classifier.py"],
    "sup.triage_summary": ["infrastructure/observability/operator_messages.py"],
    "sup.runbooks": ["docs/support_triage.md", "infrastructure/observability/runbook_registry.py"],
    "sup.operator_diagnostics": ["infrastructure/security/minimizer.py"],
    "sec.redaction": ["infrastructure/security/redaction.py"],
    "sec.outbound_guards": ["infrastructure/security/outbound_policy.py"],
    "sec.replay_abuse": ["infrastructure/security/data_governance_logger.py", "config/settings.py"],
    "perf.stage_timings": ["infrastructure/performance/timing_profiler.py"],
    "perf.bottleneck": ["infrastructure/performance/bottleneck_detector.py"],
    "perf.resource_budgets": ["infrastructure/performance/resource_snapshot.py"],
    "perf.cost_efficiency": ["infrastructure/performance/cost_exporter.py"],
    "rel.contract_gates": ["application/release/release_gate_evaluator.py"],
    "rel.rollout_policy": ["application/release/rollout_policy_engine.py"],
    "rel.compatibility": ["application/release/compatibility_checker.py"],
    "doc.index": ["docs/README.md"],
    "doc.onboarding": ["docs/onboarding.md"],
    "doc.ownership_map": ["OWNERSHIP_MAP.md"],
}

def _path_exists(root: Path, rel: str) -> bool:
    return (root / rel).is_file()


def _store_playbook_status(root: Path, store_names: list[str]) -> ReadinessStatus:
    if not store_names:
        return "ready"
    ok = 0
    for s in store_names:
        p = root / "docs" / "stores" / f"{s.strip().lower()}.md"
        if p.is_file():
            ok += 1
    if ok == len(store_names):
        return "ready"
    if ok > 0:
        return "partial"
    return "not_started"


def _status_from_paths(root: Path, rels: list[str]) -> ReadinessStatus:
    exists = [r for r in rels if _path_exists(root, r)]
    if len(exists) == len(rels) and rels:
        return "ready"
    if exists:
        return "partial"
    return "not_started"


def update_checklist_status_from_evidence(
    checklist: list[ReadinessChecklistItem],
    evidence: list[ReadinessEvidence],
    project_root: str,
    *,
    store_names: list[str] | None = None,
) -> list[ReadinessChecklistItem]:
    """Refresh item statuses from filesystem paths and coarse evidence (mutates copies)."""
    root = Path(project_root)
    stores = [s.strip() for s in (store_names or list(settings.STORE_NAMES)) if s.strip()]
    out: list[ReadinessChecklistItem] = []
    ev_valid_domains = {e.domain for e in evidence if e.valid}

    for item in checklist:
        it = item.model_copy()
        if item.item_code == "doc.store_playbooks":
            it.status = _store_playbook_status(root, stores)
        elif item.item_code in _ITEM_PATHS_READY:
            it.status = _status_from_paths(root, _ITEM_PATHS_READY[item.item_code])
        else:
            it.status = "partial" if item.domain in ev_valid_domains else "not_started"

        out.append(it)
    return out


def _gap_code(item: ReadinessChecklistItem) -> str:
    return f"gap.{item.item_code}"


def assess_readiness_gaps(
    checklist: list[ReadinessChecklistItem],
    evidence: list[ReadinessEvidence],
) -> list[ReadinessGap]:
    """Derive gaps from checklist items that are not production-ready."""
    _ = evidence
    gaps: list[ReadinessGap] = []
    for item in checklist:
        if not item.required:
            continue
        if item.status == "ready":
            continue
        sev = item.risk_if_missing
        if item.status == "not_started" and sev == "high":
            sev = "critical" if item.domain in ("security", "crm_integration") else "high"

        critical_codes = (
            "batch.partial_success",
            "replay.idempotency_key",
            "crm.payload_contract",
            "rel.contract_gates",
        )
        if item.status == "not_started":
            blocking = (
                item.risk_if_missing == "critical"
                or item.domain in ("security", "crm_integration")
                or item.item_code == "doc.store_playbooks"
                or item.item_code in critical_codes
            )
        elif item.status == "partial":
            blocking = item.domain in ("security", "crm_integration") or item.item_code == "doc.store_playbooks"
        else:
            blocking = item.status == "blocked"

        gaps.append(
            ReadinessGap(
                domain=item.domain,
                gap_code=_gap_code(item),
                description=f"{item.title}: status={item.status} — {item.description[:120]}",
                severity=sev,
                blocking=blocking,
                recommended_next_step=f"Close {item.item_code}: add tests, docs, or implementation; see docs/production_readiness.md",
            )
        )
    return gaps


def infer_blocking_gaps(gaps: list[ReadinessGap]) -> list[ReadinessGap]:
    return [g for g in gaps if g.blocking]
