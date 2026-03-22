from __future__ import annotations

import re

from domain.codebase_governance import CodePlacementDecision, LayerName, ResponsibilityArea


def get_responsibility_areas() -> list[ResponsibilityArea]:
    return [
        ResponsibilityArea(
            name="store_pdp_extraction",
            owner_layer="infrastructure",
            examples=["infrastructure/spiders/mediapark.py", "infrastructure/spiders/uzum.py"],
            anti_examples=["application/normalization/light_normalizer.py"],
        ),
        ResponsibilityArea(
            name="spec_alias_registry",
            owner_layer="application",
            examples=["application/extractors/spec_alias_registry.py", "application/extractors/spec_registry_*.py"],
            anti_examples=["domain/raw_product.py holding store-specific dicts"],
        ),
        ResponsibilityArea(
            name="lifecycle_event_selection",
            owner_layer="application",
            examples=["application/lifecycle/lifecycle_builder.py", "application/lifecycle/lifecycle_policy.py"],
            anti_examples=["infrastructure/spiders/base.py embedding CRM event rules"],
        ),
        ResponsibilityArea(
            name="crm_http_transport",
            owner_layer="infrastructure",
            examples=["infrastructure/transports/crm_http_transport.py"],
            anti_examples=["spiders calling httpx to CRM directly"],
        ),
        ResponsibilityArea(
            name="runtime_identity_bridge",
            owner_layer="infrastructure",
            examples=["infrastructure/sync/runtime_identity_bridge.py"],
            anti_examples=["domain/ storing DB ids"],
        ),
        ResponsibilityArea(
            name="security_redaction",
            owner_layer="infrastructure",
            examples=["infrastructure/security/redaction.py", "infrastructure/security/minimizer.py"],
            anti_examples=["logging full JSON blobs in spiders"],
        ),
        ResponsibilityArea(
            name="release_quality_gates",
            owner_layer="application",
            examples=["application/release/release_gate_evaluator.py"],
            anti_examples=["tests/conftest.py defining production gates"],
        ),
        ResponsibilityArea(
            name="pydantic_contracts",
            owner_layer="domain",
            examples=["domain/parser_event.py", "domain/raw_product.py"],
            anti_examples=["infrastructure/pipelines defining CRM entity schema"],
        ),
    ]


def decide_code_placement(logic_name: str, description: str) -> CodePlacementDecision:
    """Heuristic placement hint for new work (9A); not a substitute for review."""
    text = f"{logic_name} {description}".lower()
    layer: LayerName
    module = "TBD"
    reason = "Default heuristic mapping."

    if re.search(r"\b(spider|pdp|listing|html|xpath|playwright)\b", text):
        layer = "infrastructure"
        module = "infrastructure/spiders/<store>.py"
        reason = "Crawl and extraction stay in store spiders."
    elif re.search(r"\b(alias|spec registry|typed_specs|mapper)\b", text):
        layer = "application"
        module = "application/extractors/"
        reason = "Spec and alias logic is centralized in extractors."
    elif re.search(r"\b(lifecycle|product_found|idempotency|replay)\b", text):
        layer = "application"
        module = "application/lifecycle/"
        reason = "Event selection and replay policy belong in lifecycle."
    elif re.search(r"\b(crm|transport|batch|httpx|sync)\b", text) and "log" not in text:
        layer = "infrastructure"
        module = "infrastructure/transports/ or infrastructure/pipelines/"
        reason = "Outbound CRM I/O lives in transports and delivery pipelines."
    elif re.search(r"\b(bridge|registry|in[- ]memory)\b", text):
        layer = "infrastructure"
        module = "infrastructure/sync/"
        reason = "Run-scoped bridges are infrastructure adapters."
    elif re.search(r"\b(redact|ssrf|token|secret|guard)\b", text):
        layer = "infrastructure"
        module = "infrastructure/security/"
        reason = "Security controls stay in the security package."
    elif re.search(r"\b(release|gate|compat|migration)\b", text):
        layer = "application"
        module = "application/release/"
        reason = "Release and compatibility policy is application-layer."
    elif re.search(r"\b(pydantic|model|contract|schema)\b", text):
        layer = "domain"
        module = "domain/"
        reason = "Shared shapes and enums are domain contracts."
    else:
        layer = "application"
        module = "application/ (narrow module after design)"
        reason = "Prefer application orchestration unless clearly IO or domain data."

    return CodePlacementDecision(
        logic_name=logic_name,
        recommended_layer=layer,
        recommended_module=module,
        reason=reason,
    )
