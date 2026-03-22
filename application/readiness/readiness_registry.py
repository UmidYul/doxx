from __future__ import annotations

from domain.production_readiness import ReadinessChecklistItem, ReadinessDomain, ReadinessStatus


def _item(
    domain: ReadinessDomain,
    item_code: str,
    title: str,
    description: str,
    *,
    required: bool = True,
    status: ReadinessStatus = "not_started",
    risk_if_missing: str = "high",
    evidence_required: list[str] | None = None,
) -> ReadinessChecklistItem:
    from domain.production_readiness import EvidenceType, RiskLevel

    ev: list[EvidenceType] = list(evidence_required or ["unit_tests"])  # type: ignore[list-item]
    rl: RiskLevel = risk_if_missing  # type: ignore[assignment]
    return ReadinessChecklistItem(
        domain=domain,
        item_code=item_code,
        title=title,
        description=description,
        required=required,
        status=status,
        risk_if_missing=rl,
        evidence_required=ev,
    )


def get_default_readiness_checklist() -> list[ReadinessChecklistItem]:
    """Formal checklist for parser → CRM production readiness (10A)."""
    return [
        _item(
            "crawl",
            "crawl.traversal_framework",
            "Store traversal framework",
            "Shared spider/base patterns and Scrapy integration for listing→PDP flow.",
            evidence_required=["unit_tests", "config"],
        ),
        _item(
            "crawl",
            "crawl.duplicate_protection",
            "Duplicate protection",
            "In-memory dedupe / skip duplicate payloads in crawl or sync path.",
            evidence_required=["unit_tests", "config"],
        ),
        _item(
            "crawl",
            "crawl.pagination_safety",
            "Pagination stop safety",
            "Max pages / empty-page guards to limit runaway crawls.",
            evidence_required=["config", "unit_tests"],
        ),
        _item(
            "crawl",
            "crawl.store_acceptance",
            "Acceptance tests for enabled stores",
            "Regression or acceptance coverage for configured STORE_NAMES.",
            evidence_required=["acceptance_tests", "fixtures"],
        ),
        _item(
            "normalization",
            "norm.hybrid_payload",
            "Hybrid raw + typed payload",
            "NormalizedProduct carries raw_specs and typed partials for CRM.",
            evidence_required=["unit_tests", "contract_tests"],
        ),
        _item(
            "normalization",
            "norm.typed_mapping",
            "Typed spec partial mapping",
            "Deterministic map_raw_specs → typed fields with coverage metadata.",
            evidence_required=["unit_tests", "fixtures"],
        ),
        _item(
            "normalization",
            "norm.confidence_suppression",
            "Confidence / suppression",
            "Low-confidence typed fields suppressed per policy.",
            evidence_required=["unit_tests"],
        ),
        _item(
            "normalization",
            "norm.low_coverage_detection",
            "Low coverage detectable",
            "Warnings/metrics when mapping ratio falls below threshold.",
            evidence_required=["unit_tests", "metrics"],
        ),
        _item(
            "crm_integration",
            "crm.transport",
            "CRM HTTP transport",
            "CrmHttpTransport (or configured transport) for sync delivery.",
            evidence_required=["unit_tests", "config"],
            risk_if_missing="critical",
        ),
        _item(
            "crm_integration",
            "crm.auth",
            "Parser authentication",
            "Parser key / signing hooks for outbound CRM requests.",
            evidence_required=["config", "unit_tests"],
            risk_if_missing="critical",
        ),
        _item(
            "crm_integration",
            "crm.payload_contract",
            "Payload contract tests",
            "Contract tests guard parser event / payload shapes.",
            evidence_required=["contract_tests"],
            risk_if_missing="critical",
        ),
        _item(
            "lifecycle",
            "life.product_found_default",
            "product_found safe default",
            "Default lifecycle event is product_found unless policy allows deltas.",
            evidence_required=["unit_tests", "docs"],
        ),
        _item(
            "lifecycle",
            "life.fallback_policy",
            "Fallback / downgrade policy",
            "Delta → product_found downgrade when replay safety requires it.",
            evidence_required=["unit_tests", "docs"],
        ),
        _item(
            "lifecycle",
            "life.lifecycle_tests",
            "Lifecycle unit/integration tests",
            "Tests for lifecycle_builder, replay, idempotency surfaces.",
            evidence_required=["unit_tests"],
        ),
        _item(
            "batch_apply",
            "batch.partial_success",
            "Partial batch success semantics",
            "Batch coordinator allows partial success per policy.",
            evidence_required=["unit_tests"],
            risk_if_missing="critical",
        ),
        _item(
            "batch_apply",
            "batch.retryable",
            "Retryable item handling",
            "Retry/requeue for retryable CRM outcomes.",
            evidence_required=["unit_tests"],
            risk_if_missing="high",
        ),
        _item(
            "batch_apply",
            "batch.duplicate_skip",
            "Duplicate payload skip",
            "Runtime skip of duplicate entity+payload when enabled.",
            evidence_required=["unit_tests"],
        ),
        _item(
            "replay_reconciliation",
            "replay.idempotency_key",
            "Idempotency key",
            "Request idempotency key generated and aligned with payload scope.",
            evidence_required=["unit_tests", "config"],
            risk_if_missing="critical",
        ),
        _item(
            "replay_reconciliation",
            "replay.replay_safe_product_found",
            "Replay-safe product_found",
            "Policy allows safe resend of product_found where configured.",
            evidence_required=["unit_tests", "docs"],
        ),
        _item(
            "replay_reconciliation",
            "replay.reconciliation",
            "Reconciliation path",
            "Reconciliation flows for missing/ambiguous CRM responses.",
            evidence_required=["unit_tests"],
        ),
        _item(
            "observability",
            "obs.structured_traces",
            "Structured sync traces",
            "Structured sync_event / correlation logging.",
            evidence_required=["unit_tests", "metrics"],
        ),
        _item(
            "observability",
            "obs.batch_traces",
            "Batch traces",
            "Batch trace records when enabled.",
            evidence_required=["config", "unit_tests"],
        ),
        _item(
            "observability",
            "obs.etl_export",
            "ETL / diagnostic export surfaces",
            "Operator/triage export or snapshot builders.",
            evidence_required=["unit_tests", "metrics"],
        ),
        _item(
            "observability",
            "obs.failure_classification",
            "Failure classification",
            "Classify apply/HTTP/normalization failures for routing.",
            evidence_required=["unit_tests"],
        ),
        _item(
            "supportability",
            "sup.triage_summary",
            "Triage summary",
            "Triage summary builders for operator messages.",
            evidence_required=["unit_tests", "runbook"],
        ),
        _item(
            "supportability",
            "sup.runbooks",
            "Runbook / support docs",
            "Support triage doc and runbook-style guidance.",
            evidence_required=["docs", "runbook"],
        ),
        _item(
            "supportability",
            "sup.operator_diagnostics",
            "Operator-safe diagnostics",
            "Minimized/redacted diagnostics suitable for support.",
            evidence_required=["docs", "unit_tests"],
        ),
        _item(
            "security",
            "sec.redaction",
            "Secret / payload redaction",
            "Redaction applied to logs and exports.",
            evidence_required=["unit_tests", "config"],
            risk_if_missing="critical",
        ),
        _item(
            "security",
            "sec.outbound_guards",
            "Outbound URL / proxy guards",
            "SSRF/outbound policy and optional proxy validation.",
            evidence_required=["unit_tests", "config"],
            risk_if_missing="critical",
        ),
        _item(
            "security",
            "sec.replay_abuse",
            "Replay abuse guard",
            "Guards against abusive replay patterns where implemented.",
            evidence_required=["unit_tests", "config"],
            risk_if_missing="high",
        ),
        _item(
            "performance",
            "perf.stage_timings",
            "Stage timings",
            "Performance profiling hooks for pipeline stages.",
            evidence_required=["metrics", "unit_tests"],
        ),
        _item(
            "performance",
            "perf.bottleneck",
            "Bottleneck detection",
            "Signals when stages exceed thresholds.",
            evidence_required=["metrics", "unit_tests"],
        ),
        _item(
            "performance",
            "perf.resource_budgets",
            "Resource budgets",
            "Store/browser/proxy budgets or admission control.",
            evidence_required=["config", "unit_tests"],
        ),
        _item(
            "performance",
            "perf.cost_efficiency",
            "Cost / efficiency policy",
            "Cost-efficiency signals and gates (8C).",
            evidence_required=["metrics", "unit_tests"],
        ),
        _item(
            "release_governance",
            "rel.contract_gates",
            "Contract / release gates",
            "release_gate_evaluator and related CI flags.",
            evidence_required=["unit_tests", "config"],
            risk_if_missing="critical",
        ),
        _item(
            "release_governance",
            "rel.rollout_policy",
            "Rollout policy",
            "Feature/store rollout policy engine present.",
            evidence_required=["unit_tests", "config"],
        ),
        _item(
            "release_governance",
            "rel.compatibility",
            "Compatibility checks",
            "Compatibility / migration readiness modules for contract evolution.",
            evidence_required=["unit_tests"],
            risk_if_missing="high",
        ),
        _item(
            "documentation",
            "doc.index",
            "Documentation index",
            "docs/README.md navigates major topics.",
            evidence_required=["docs"],
        ),
        _item(
            "documentation",
            "doc.onboarding",
            "Onboarding guide",
            "docs/onboarding.md for new engineers.",
            evidence_required=["docs"],
        ),
        _item(
            "documentation",
            "doc.store_playbooks",
            "Store playbooks for enabled stores",
            "docs/stores/<store>.md for each STORE_NAMES entry.",
            evidence_required=["docs"],
        ),
        _item(
            "documentation",
            "doc.ownership_map",
            "Ownership map",
            "OWNERSHIP_MAP.md defines areas and escalation.",
            evidence_required=["docs"],
        ),
    ]


def get_required_items_only() -> list[ReadinessChecklistItem]:
    return [x for x in get_default_readiness_checklist() if x.required]


def get_domain_checklist(domain: str) -> list[ReadinessChecklistItem]:
    return [x for x in get_default_readiness_checklist() if x.domain == domain]
