from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import urlparse

import orjson

from application.extractors.spec_label_normalizer import normalize_spec_label
from application.normalization.light_normalizer import extract_compatibility_targets
from config.settings import settings
from domain.crm_sync import CrmSyncItem
from domain.parser_event import ParserEventType, ParserSyncEvent

_WS_RE = re.compile(r"\s+")


def canonicalize_url(url: str) -> str:
    """Strip query/fragment, lowercase netloc — stable across scrape runs."""
    p = urlparse(url.strip())
    netloc = (p.netloc or "").lower()
    path = p.path or "/"
    return f"{p.scheme}://{netloc}{path}"


def build_entity_key(store: str, source_id: str | None, url: str) -> str:
    sid = (source_id or "").strip()
    if sid:
        return f"{store}:{sid}"
    h = hashlib.sha256(canonicalize_url(url).encode()).hexdigest()[:16]
    return f"{store}:{h}"


def _normalize_title(title: str) -> str:
    return _WS_RE.sub(" ", (title or "").strip())


def _build_normalized_spec_labels(raw_specs: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw_label in raw_specs.keys():
        label = str(raw_label).strip()
        if not label:
            continue
        normalized = normalize_spec_label(label)
        if normalized:
            out[label] = normalized
    return out


def build_payload_hash(
    *,
    schema_version: int,
    store: str,
    url: str,
    title: str,
    source_id: str | None,
    external_ids: dict[str, str],
    barcode: str | None,
    model_name: str | None,
    category_hint: str | None,
    price_raw: str | None,
    price_value: int | None,
    currency: str | None,
    in_stock: bool | None,
    brand: str | None,
    raw_specs: dict[str, Any],
    typed_specs: dict[str, Any],
    normalization_warnings: list[str],
    description: str | None,
    image_urls: list[str],
) -> str:
    """SHA-256 over business-only fields (no scraped_at)."""
    ext_sorted = {k: external_ids[k] for k in sorted(external_ids.keys())}
    ts = dict(typed_specs or {})
    typed_sorted = {k: ts[k] for k in sorted(ts.keys())}
    normalized_spec_labels = _build_normalized_spec_labels(raw_specs)
    normalized_spec_labels_sorted = {
        k: normalized_spec_labels[k] for k in sorted(normalized_spec_labels.keys())
    }
    compatibility_targets = extract_compatibility_targets(
        title,
        category_hint=category_hint,
        raw_specs=raw_specs,
    )
    nw = sorted(str(x) for x in (normalization_warnings or []) if str(x).strip())
    blob = {
        "schema_version": schema_version,
        "store": store,
        "url": canonicalize_url(url),
        "title": _normalize_title(title),
        "source_id": source_id if source_id else None,
        "external_ids": ext_sorted,
        "barcode": barcode,
        "model_name": model_name,
        "category_hint": category_hint,
        "price_raw": price_raw,
        "price_value": price_value,
        "currency": currency,
        "in_stock": in_stock,
        "brand": brand,
        "raw_specs": raw_specs,
        "normalized_spec_labels": normalized_spec_labels_sorted,
        "compatibility_targets": compatibility_targets,
        "typed_specs": typed_sorted,
        "normalization_warnings": nw,
        "description": description,
        "image_urls": sorted(set(image_urls)),
    }
    raw = orjson.dumps(blob, option=orjson.OPT_SORT_KEYS)
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _compute_change_hint(
    *, price_value: int | None, in_stock: bool | None, raw_specs: dict[str, Any]
) -> str | None:
    if in_stock is False:
        return "stock_update"
    if price_value is not None:
        return "price_update"
    if not raw_specs:
        return "new_product"
    return None


def build_crm_sync_item(normalized: dict[str, Any]) -> CrmSyncItem:
    """Build a :class:`CrmSyncItem` from a ``_normalized`` dict.

    Soft-degrades when optional keys are missing (older payloads).
    """
    store = normalized.get("store") or ""
    url = normalized.get("url") or ""
    title_clean = (normalized.get("title_clean") or normalized.get("title") or "").strip()
    title_for_item = title_clean or str(normalized.get("title") or "")

    source_id = normalized.get("source_id") or None
    if isinstance(source_id, str) and not source_id.strip():
        source_id = None

    external_ids: dict[str, str] = dict(normalized.get("external_ids") or {})
    if not external_ids and source_id and store:
        external_ids = {store: source_id}

    barcode = normalized.get("barcode")
    if barcode is not None and isinstance(barcode, str) and not barcode.strip():
        barcode = None

    model_name = normalized.get("model_name")
    if model_name is not None and isinstance(model_name, str) and not model_name.strip():
        model_name = None

    category_hint = normalized.get("category_hint")
    if category_hint is not None and str(category_hint).strip() == "":
        category_hint = None

    price_raw = normalized.get("price_raw")
    price_value = normalized.get("price_value")
    if isinstance(price_value, bool):
        price_value = None
    if price_value is None and normalized.get("price") is not None:
        try:
            price_value = int(round(float(normalized["price"])))
        except (TypeError, ValueError):
            price_value = None

    currency = normalized.get("currency") or settings.DEFAULT_CURRENCY
    in_stock = normalized.get("in_stock")
    brand = normalized.get("brand")

    raw_specs: dict[str, Any] = dict(normalized.get("raw_specs") or {})
    raw_specs.pop("_category_hint", None)
    normalized_spec_labels = _build_normalized_spec_labels(raw_specs)
    compatibility_targets = extract_compatibility_targets(
        title_for_item,
        category_hint=category_hint,
        raw_specs=raw_specs,
    )

    typed_specs: dict[str, Any] = dict(normalized.get("typed_specs") or {})
    normalization_warnings: list[str] = [
        str(w).strip() for w in (normalized.get("normalization_warnings") or []) if str(w).strip()
    ]

    spec_coverage: dict[str, Any] = {}
    if settings.CRM_INCLUDE_SPEC_COVERAGE:
        spec_coverage = dict(normalized.get("spec_coverage") or {})

    field_confidence: dict[str, Any] = {}
    if settings.CRM_INCLUDE_FIELD_CONFIDENCE:
        field_confidence = dict(normalized.get("field_confidence") or {})

    suppressed_typed_fields: list[dict[str, Any]] = []
    if settings.CRM_INCLUDE_SUPPRESSED_TYPED_FIELDS:
        suppressed_typed_fields = [dict(x) for x in (normalized.get("suppressed_typed_fields") or []) if x]

    normalization_quality: dict[str, Any] = {}
    if settings.CRM_INCLUDE_NORMALIZATION_QUALITY:
        normalization_quality = dict(normalized.get("normalization_quality") or {})

    description = normalized.get("description")
    image_urls: list[str] = list(normalized.get("image_urls") or [])

    schema_version = settings.MESSAGE_SCHEMA_VERSION
    entity_key = build_entity_key(store, source_id, url)
    payload_hash = build_payload_hash(
        schema_version=schema_version,
        store=store,
        url=url,
        title=title_for_item,
        source_id=source_id,
        external_ids=external_ids,
        barcode=barcode if isinstance(barcode, str) else None,
        model_name=model_name if isinstance(model_name, str) else None,
        category_hint=category_hint if isinstance(category_hint, str) else None,
        price_raw=price_raw if isinstance(price_raw, str) else None,
        price_value=price_value if isinstance(price_value, int) and not isinstance(price_value, bool) else None,
        currency=currency if isinstance(currency, str) else None,
        in_stock=in_stock if in_stock is None or isinstance(in_stock, bool) else None,
        brand=brand if isinstance(brand, str) else None,
        raw_specs=raw_specs,
        typed_specs=typed_specs,
        normalization_warnings=normalization_warnings,
        description=description if isinstance(description, str) else None,
        image_urls=image_urls,
    )
    hint = _compute_change_hint(price_value=price_value, in_stock=in_stock, raw_specs=raw_specs)

    return CrmSyncItem(
        schema_version=schema_version,
        entity_key=entity_key,
        payload_hash=payload_hash,
        source_name=store,
        source_url=url.strip(),
        source_id=source_id,
        external_ids=external_ids,
        title=_normalize_title(title_for_item),
        brand=brand,
        category_hint=category_hint if isinstance(category_hint, str) else None,
        price_value=price_value if isinstance(price_value, int) and not isinstance(price_value, bool) else None,
        price_raw=price_raw if isinstance(price_raw, str) else None,
        currency=currency if isinstance(currency, str) else None,
        in_stock=in_stock if in_stock is None or isinstance(in_stock, bool) else None,
        raw_specs=raw_specs,
        normalized_spec_labels=normalized_spec_labels,
        compatibility_targets=compatibility_targets,
        typed_specs=typed_specs,
        normalization_warnings=normalization_warnings,
        spec_coverage=spec_coverage,
        field_confidence=field_confidence,
        suppressed_typed_fields=suppressed_typed_fields,
        normalization_quality=normalization_quality,
        description=description if isinstance(description, str) else None,
        image_urls=image_urls,
        scraped_at=datetime.now(UTC),
        barcode=barcode if isinstance(barcode, str) else None,
        model_name=model_name if isinstance(model_name, str) else None,
        sync_mode="snapshot",
        change_hint=hint,
    )


def resolve_parser_event_type(sync_item: CrmSyncItem) -> ParserEventType:
    """Operational event type; stateless safe default is always ``product_found``."""
    allowed: tuple[ParserEventType, ...] = (
        "product_found",
        "price_changed",
        "out_of_stock",
        "characteristic_added",
    )
    default: ParserEventType = (
        cast(ParserEventType, settings.PARSER_EVENT_DEFAULT_TYPE)
        if settings.PARSER_EVENT_DEFAULT_TYPE in allowed
        else "product_found"
    )
    if not settings.PARSER_ENABLE_DELTA_EVENTS:
        return "product_found"
    ch = sync_item.change_hint
    if settings.PARSER_ENABLE_PRICE_CHANGED_EVENT and ch == "price_update":
        return "price_changed"
    if settings.PARSER_ENABLE_OUT_OF_STOCK_EVENT and ch == "stock_update":
        return "out_of_stock"
    if settings.PARSER_ENABLE_CHARACTERISTIC_ADDED_EVENT and ch == "spec_update":
        return "characteristic_added"
    return default


def dump_crm_sync_item_for_export(item: CrmSyncItem) -> dict[str, Any]:
    """Serialize ``CrmSyncItem`` to JSON-ready dict with optional shadow/dual-shape (6C)."""
    from application.release.shape_compat import apply_export_compatibility

    return apply_export_compatibility("crm_payload", item.model_dump(mode="json"))


def build_parser_sync_event(normalized: dict[str, Any]) -> ParserSyncEvent:
    """Build envelope via lifecycle policy (no runtime CRM ids — safe ``product_found`` default)."""
    from application.lifecycle.lifecycle_builder import build_lifecycle_event, parser_sync_event_from_lifecycle

    ple, _decision = build_lifecycle_event(normalized, runtime_ids=None, requested_event_type=None)
    return parser_sync_event_from_lifecycle(ple, normalized_for_reconcile=dict(normalized))
