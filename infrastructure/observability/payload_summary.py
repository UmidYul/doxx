from __future__ import annotations

from typing import Any

from config.settings import settings
from domain.crm_apply_result import CrmApplyResult
from infrastructure.security.redaction import minimize_url_for_support, redact_payload


def summarize_normalized_payload(normalized: dict[str, Any]) -> dict[str, object]:
    """Compact, non-PII-heavy summary for structured logs (not full raw payload)."""
    price_val = normalized.get("price_value")
    has_price = price_val is not None and str(price_val).strip() != ""
    brand = normalized.get("brand")
    has_brand = brand is not None and str(brand).strip() != ""
    barcode = normalized.get("barcode")
    has_barcode = barcode is not None and str(barcode).strip() != ""

    typed = normalized.get("typed_specs") or {}
    if hasattr(typed, "model_dump"):
        typed = typed.model_dump(mode="json")
    typed_specs_count = len(typed) if isinstance(typed, dict) else 0

    raw_specs = normalized.get("raw_specs") or {}
    raw_specs_count = len(raw_specs) if isinstance(raw_specs, dict) else 0

    nw = normalized.get("normalization_warnings") or []
    normalization_warning_count = len(nw) if isinstance(nw, list) else 0

    suppressed = normalized.get("suppressed_typed_fields") or []
    suppressed_fields_count = len(suppressed) if isinstance(suppressed, list) else 0

    cov = normalized.get("spec_coverage") if isinstance(normalized.get("spec_coverage"), dict) else {}
    category_hint = normalized.get("category_hint")
    if isinstance(category_hint, str) and getattr(settings, "ENABLE_DATA_MINIMIZATION", True):
        category_hint = minimize_url_for_support(
            category_hint,
            full_query_allowed=bool(getattr(settings, "SUPPORT_EXPORT_INCLUDE_FULL_URL_QUERY", False)),
        )

    summary = {
        "has_price": bool(has_price),
        "has_brand": bool(has_brand),
        "has_barcode": bool(has_barcode),
        "typed_specs_count": typed_specs_count,
        "raw_specs_count": raw_specs_count,
        "normalization_warning_count": normalization_warning_count,
        "suppressed_fields_count": suppressed_fields_count,
        "category_hint": category_hint,
        "event_type": None,
        "action": None,
        "ids_present": {
            "source_id": bool((normalized.get("source_id") or "").strip() if isinstance(normalized.get("source_id"), str) else normalized.get("source_id")),
            "entity_key_hint": bool(normalized.get("external_ids")),
        },
        "spec_coverage_enabled": bool(cov.get("enabled", True)),
        "mapped_fields_count": cov.get("mapped_fields_count"),
        "unmapped_fields_count": cov.get("unmapped_fields_count"),
    }
    if getattr(settings, "DEV_MODE", False):
        summary = {**summary, "dev_tag": "moscraper_dx_v1"}
    return summary


def summarize_apply_result(result: object) -> dict[str, object]:
    """Summary of CRM apply outcome for logs (no full CRM body)."""
    if not isinstance(result, CrmApplyResult):
        return redact_payload({"recognized": False, "type": type(result).__name__})
    summ = {
        "recognized": True,
        "success": result.success,
        "status": result.status,
        "http_status": result.http_status,
        "retryable": result.retryable,
        "action": result.action,
        "has_listing_id": result.crm_listing_id is not None,
        "has_product_id": result.crm_product_id is not None,
        "reconciliation_signal": result.parser_reconciliation_signal,
        "error_code": result.error_code,
    }
    return redact_payload(summ)
