from __future__ import annotations

_KNOWN = {
    "spider_contains_business_normalization": (
        "Spider code should extract raw structured fields; deterministic normalization belongs in "
        "application/normalization or pipelines, not in spider methods."
    ),
    "spider_contains_transport_logic": (
        "Spiders schedule HTTP/browser requests; CRM transport and batching belong in "
        "infrastructure/transports and sync pipelines."
    ),
    "pipeline_contains_store_specific_parsing": (
        "Item pipelines should be store-agnostic; store quirks belong in infrastructure/spiders "
        "or application policies keyed by store."
    ),
    "transport_contains_catalog_matching_logic": (
        "HTTP transports deliver payloads; catalog or entity matching belongs in application/ "
        "or CRM consumer logic."
    ),
    "observability_contains_business_mutation": (
        "Logging/metrics should observe; they must not mutate business entities or payloads."
    ),
    "config_contains_runtime_decision_logic": (
        "config/settings holds declarations; branching crawl/runtime decisions belong in "
        "application or infrastructure code."
    ),
    "duplicated_alias_registry": (
        "Centralize alias and spec mappings in application/extractors registries; avoid copy-paste "
        "dictionaries across spiders."
    ),
    "duplicated_event_selection_logic": (
        "Lifecycle event selection should live in application/lifecycle; do not fork selection "
        "rules per spider."
    ),
    "direct_cross_layer_import": (
        "Respect layer boundaries (see ARCHITECTURE_MAP.md and dependency_policy.get_default_boundary_rules)."
    ),
    "unbounded_runtime_buffer": (
        "Avoid unbounded in-memory buffers for scraped listings; parser is stateless per PROJECT.md."
    ),
    "raw_payload_logged_directly": (
        "Never log raw payloads without redaction/minimization; use infrastructure/security helpers."
    ),
}


def list_known_anti_patterns() -> list[str]:
    return sorted(_KNOWN.keys())


def explain_anti_pattern(name: str) -> str:
    return _KNOWN.get(
        name,
        "Unknown anti-pattern id; see docs/adr and CODE_STANDARDS.md.",
    )


def suggest_refactor_for_anti_pattern(name: str) -> list[str]:
    ex = explain_anti_pattern(name)
    base = [f"Context: {ex}"]
    if name == "spider_contains_business_normalization":
        return base + [
            "Move normalization helpers to application/normalization/",
            "Keep spider output close to RawProduct / domain shapes",
        ]
    if name == "spider_contains_transport_logic":
        return base + [
            "Use infrastructure/transports for CRM HTTP",
            "Keep sync orchestration in infrastructure/pipelines/sync_pipeline.py",
        ]
    if name == "pipeline_contains_store_specific_parsing":
        return base + [
            "Gate store-specific behavior via store profiles or spider-only code",
            "Keep pipeline stages generic",
        ]
    if name == "transport_contains_catalog_matching_logic":
        return base + [
            "Return structured apply results; move matching to application/lifecycle or CRM",
        ]
    if name == "observability_contains_business_mutation":
        return base + [
            "Log copies of minimized fields; do not mutate items in loggers",
        ]
    if name == "config_contains_runtime_decision_logic":
        return base + [
            "Expose booleans/thresholds in Settings; implement decision in application/",
        ]
    if name == "direct_cross_layer_import":
        return base + [
            "Run application/governance/architecture_lint.py helpers in CI",
            "Invert dependency or extract interface to domain/",
        ]
    if name == "unbounded_runtime_buffer":
        return base + [
            "Stream to broker; use bounded queues with backpressure (resource governance)",
        ]
    if name == "raw_payload_logged_directly":
        return base + [
            "Route through infrastructure/security/minimizer and redaction",
        ]
    return base + ["Review ARCHITECTURE_MAP.md for placement."]
