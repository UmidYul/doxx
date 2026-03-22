from __future__ import annotations

from domain.data_governance import DataFieldPolicy, DataUsagePurpose

_ALL_PURPOSES: list[DataUsagePurpose] = [
    "crawl",
    "normalize",
    "delivery",
    "observability",
    "support",
    "replay",
]
_OPS: list[DataUsagePurpose] = ["observability", "support", "delivery"]
_NO_SUPPORT: list[DataUsagePurpose] = ["crawl", "normalize", "delivery", "observability", "replay"]


def _p(
    name: str,
    *,
    sensitivity: str,
    loggable: bool = True,
    exportable: bool = True,
    redact_required: bool = False,
    allowed_purposes: list[DataUsagePurpose] | None = None,
) -> DataFieldPolicy:
    return DataFieldPolicy(
        field_name=name,
        sensitivity=sensitivity,  # type: ignore[arg-type]
        allowed_purposes=list(allowed_purposes or _ALL_PURPOSES),
        loggable=loggable,
        exportable=exportable,
        redact_required=redact_required,
    )


FIELD_POLICIES: dict[str, DataFieldPolicy] = {
    "source_url": _p("source_url", sensitivity="sensitive", allowed_purposes=_OPS + ["crawl", "normalize"]),
    "source_id": _p("source_id", sensitivity="internal"),
    "entity_key": _p("entity_key", sensitivity="internal"),
    "payload_hash": _p("payload_hash", sensitivity="internal"),
    "request_idempotency_key": _p("request_idempotency_key", sensitivity="sensitive", redact_required=True),
    "crm_listing_id": _p("crm_listing_id", sensitivity="internal"),
    "crm_product_id": _p("crm_product_id", sensitivity="internal"),
    "raw_specs": _p("raw_specs", sensitivity="sensitive", loggable=False, exportable=True, allowed_purposes=_OPS + ["normalize"]),
    "typed_specs": _p("typed_specs", sensitivity="internal", allowed_purposes=_OPS + ["normalize"]),
    "normalization_warnings": _p("normalization_warnings", sensitivity="internal", allowed_purposes=_OPS + ["normalize"]),
    "field_confidence": _p("field_confidence", sensitivity="sensitive", loggable=False, exportable=False, allowed_purposes=["observability"]),
    "suppressed_typed_fields": _p("suppressed_typed_fields", sensitivity="sensitive", loggable=False, exportable=False, allowed_purposes=["observability"]),
    "image_urls": _p("image_urls", sensitivity="internal", allowed_purposes=_OPS + ["crawl", "normalize"]),
    "headers": _p("headers", sensitivity="restricted", loggable=False, exportable=False, allowed_purposes=["observability"]),
    "proxy_url": _p("proxy_url", sensitivity="restricted", loggable=False, exportable=False, redact_required=True),
    "parser_key": _p("parser_key", sensitivity="restricted", loggable=False, exportable=False, redact_required=True),
    "signature_headers": _p("signature_headers", sensitivity="restricted", loggable=False, exportable=False, redact_required=True),
    "diagnostic_snapshot": _p("diagnostic_snapshot", sensitivity="internal", allowed_purposes=_OPS),
    "etl_status_payload": _p("etl_status_payload", sensitivity="internal", allowed_purposes=["observability", "support"]),
    "category_url": _p("category_url", sensitivity="sensitive", allowed_purposes=_OPS + ["crawl"]),
    "batch_id": _p("batch_id", sensitivity="internal"),
    "event_id": _p("event_id", sensitivity="internal"),
    "title": _p("title", sensitivity="internal", allowed_purposes=_NO_SUPPORT),
    "price_raw": _p("price_raw", sensitivity="internal"),
    "barcode": _p("barcode", sensitivity="sensitive"),
    "details": _p("details", sensitivity="internal", loggable=True, exportable=False),
    "metrics": _p("metrics", sensitivity="internal"),
    "correlation": _p("correlation", sensitivity="internal"),
    "spec_coverage": _p("spec_coverage", sensitivity="internal"),
}


def get_field_policy(field_name: str) -> DataFieldPolicy | None:
    return FIELD_POLICIES.get(field_name)


def default_policy_for_unknown(field_name: str) -> DataFieldPolicy:
    return _p(field_name, sensitivity="internal", loggable=True, exportable=True)
