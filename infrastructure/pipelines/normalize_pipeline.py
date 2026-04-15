from __future__ import annotations

import json
import logging

from application.crm_sync_builder import build_entity_key
from application.extractors.spec_coverage import build_spec_coverage_report
from application.extractors.spec_mapper import map_raw_specs_to_typed_partial
from application.extractors.spec_quality import build_normalization_quality_summary
from application.release.rollout_policy_engine import is_feature_enabled
from application.extractors.spec_sanity import apply_cross_field_sanity_checks
from application.extractors.unit_normalizer import normalize_brand
from config.settings import settings
from infrastructure.observability import message_codes as obs_mc
from infrastructure.observability.correlation import build_correlation_context
from infrastructure.observability.event_logger import log_sync_event
from infrastructure.observability.failure_classifier import classify_normalization_issue
from infrastructure.observability.payload_summary import summarize_normalized_payload
from infrastructure.spiders.product_classifier import infer_known_brand
from application.normalization.light_normalizer import (
    build_external_ids,
    derive_category_hint,
    extract_barcode,
    extract_brand_from_raw_specs,
    extract_compatibility_targets,
    extract_model_name,
    extract_model_name_from_raw_specs,
    normalize_image_urls,
    normalize_price_value,
    normalize_stock_value,
    normalize_title_whitespace,
    sanitize_raw_specs,
)
from domain.normalized_product import NormalizedProduct

logger = logging.getLogger(__name__)


class NormalizePipeline:
    """Light normalization + partial typed specs for CRM match keys (hybrid payload)."""

    _dev_debug_emit_count: int = 0

    def process_item(self, item, spider):
        from infrastructure.performance.timing_profiler import timed_stage

        store = str(item.get("source", spider.store_name)).strip()
        with timed_stage(
            "normalize",
            store_name=store,
            spider_name=getattr(spider, "name", None),
        ):
            return self._process_item_inner(item, spider, store)

    def _process_item_inner(self, item, spider, store: str):
        url = item["url"].strip()
        title = (item.get("title") or item.get("name") or "").strip()
        title_clean = normalize_title_whitespace(title)

        price_str = (item.get("price_str") or "").strip()
        price_raw = price_str or None
        price_value = normalize_price_value(price_str) if price_str else None

        raw_in = dict(item.get("raw_specs") or {})
        spider_cat = item.get("category_hint") or item.get("category") or raw_in.get("_category_hint")
        raw_specs = sanitize_raw_specs(raw_in)
        raw_specs.pop("_category_hint", None)

        brand_raw = item.get("brand") or ""
        brand = normalize_brand(brand_raw) if brand_raw else None
        if not brand:
            spec_brand = extract_brand_from_raw_specs(raw_specs)
            brand = normalize_brand(spec_brand) if spec_brand else None
        if not brand:
            inferred_brand = infer_known_brand(title_clean)
            brand = normalize_brand(inferred_brand) if inferred_brand else None

        in_stock = normalize_stock_value(item.get("in_stock"))

        barcode = extract_barcode(raw_specs)
        category_hint = derive_category_hint(url, title_clean, raw_specs, spider_hint=spider_cat)
        source_id = (item.get("source_id") or "").strip() or None
        entity_key = build_entity_key(store, source_id, url)

        typed_model, map_warnings, map_meta = map_raw_specs_to_typed_partial(
            raw_specs,
            category_hint,
            store_name=store,
            source_id=source_id,
            url=url,
        )

        typed_after_sanity, sanity_warnings, sanity_suppressed = apply_cross_field_sanity_checks(
            typed_model,
            category_hint,
            store=store,
            source_id=source_id,
            url=url,
        )

        field_confidence: dict = dict(map_meta.get("field_confidence") or {})
        suppressed_typed_fields: list = list(map_meta.get("suppressed_typed_fields") or [])
        conflicting_fields: list = list(map_meta.get("conflicting_fields") or [])

        for sp in sanity_suppressed:
            sd = sp.to_compact_dict()
            suppressed_typed_fields.append(sd)
            fn = sp.field_name
            if fn in field_confidence:
                del field_confidence[fn]

        normalization_warnings = list(dict.fromkeys([*map_warnings, *sanity_warnings]))

        ratio = map_meta.get("mapping_ratio")
        quality = build_normalization_quality_summary(
            category_hint=category_hint,
            field_confidence=field_confidence,
            suppressed_typed_fields=suppressed_typed_fields,
            conflicting_fields=conflicting_fields,
            normalization_warnings=normalization_warnings,
            mapping_ratio=float(ratio) if ratio is not None else None,
            typed_specs=typed_after_sanity,
        )
        if settings.ENABLE_NORMALIZATION_QUALITY_SUMMARY and is_feature_enabled(
            "normalization_quality_metadata",
            store,
            entity_key,
        ):
            quality_dict = quality.to_compact_dict()
        else:
            quality_dict = {}

        logger.info(
            "normalize_specs %s",
            json.dumps(
                {
                    "event": "NORMALIZATION_QUALITY_BUILT",
                    "store": store,
                    "source_id": source_id,
                    "url": url,
                    "category_hint": category_hint,
                    "normalized_value": None,
                    "confidence": None,
                    "threshold": None,
                    "reason_code": None,
                    "warning_codes": normalization_warnings,
                    "mapping_ratio": ratio,
                    "normalization_quality": quality_dict,
                },
                ensure_ascii=False,
                default=str,
            ),
        )

        if settings.ENABLE_SPEC_COVERAGE_REPORT:
            map_meta_updated = {
                **map_meta,
                "field_confidence": field_confidence,
                "suppressed_typed_fields": suppressed_typed_fields,
                "conflicting_fields": conflicting_fields,
                "normalization_quality": quality_dict,
            }
            spec_coverage: dict = build_spec_coverage_report(raw_specs, typed_after_sanity, map_meta_updated)
        else:
            spec_coverage = {
                "enabled": False,
                "mapped_fields_count": map_meta.get("mapped_fields_count", 0),
                "unmapped_fields_count": map_meta.get("unmapped_fields_count", 0),
            }

        compatibility_targets = extract_compatibility_targets(
            title_clean,
            category_hint=category_hint,
            raw_specs=raw_specs,
        )
        spec_model_name = extract_model_name_from_raw_specs(
            raw_specs,
            brand=brand,
            category_hint=category_hint,
            compatibility_targets=compatibility_targets,
        )
        title_model_name = extract_model_name(title_clean, brand, category_hint)
        model_name = spec_model_name or title_model_name
        external_ids = build_external_ids(store, source_id)

        desc = item.get("description")
        description = (desc or "").strip() or None if desc is not None else None

        if normalization_warnings:
            logger.info(
                "normalize_specs %s",
                json.dumps(
                    {
                        "event": "NORMALIZATION_WARNING",
                        "store": store,
                        "source_id": source_id,
                        "url": url,
                        "category_hint": category_hint,
                        "reason_code": "batch",
                        "warning_codes": normalization_warnings,
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            )

        raw_run = getattr(spider, "_parser_run_id", None)
        run_id = raw_run if isinstance(raw_run, str) else None
        raw_name = getattr(spider, "name", None)
        spider_name = raw_name if isinstance(raw_name, str) else "unknown"
        cat_url = item.get("_listing_category_url") or item.get("category_url")
        corr = build_correlation_context(
            spider_name,
            store,
            run_id=run_id,
            category_url=str(cat_url) if cat_url else None,
            source_url=url,
            source_id=source_id,
        )
        if settings.ENABLE_DIAGNOSTIC_PAYLOAD_SUMMARY and is_feature_enabled(
            "observability_export",
            store,
            entity_key,
        ):
            ts_dump = (
                typed_after_sanity.model_dump(mode="json")
                if hasattr(typed_after_sanity, "model_dump")
                else typed_after_sanity
            )
            norm_preview = {
                "store": store,
                "url": url,
                "source_id": source_id,
                "category_hint": category_hint,
                "price_value": price_value,
                "brand": brand,
                "barcode": barcode,
                "raw_specs": raw_specs,
                "typed_specs": ts_dump,
                "normalization_warnings": normalization_warnings,
                "spec_coverage": spec_coverage,
                "suppressed_typed_fields": suppressed_typed_fields,
            }
            summ = summarize_normalized_payload(norm_preview)
        else:
            summ = {}

        log_sync_event(
            "normalize",
            "info",
            obs_mc.NORMALIZATION_COMPLETED,
            corr,
            metrics={
                "mapping_ratio": float(ratio) if ratio is not None else 0.0,
                "warning_count": len(normalization_warnings),
            },
            details=summ,
        )

        ratio_f = float(ratio) if ratio is not None else None
        if ratio_f is not None and ratio_f < float(settings.SPEC_MAPPING_MIN_COVERAGE_WARNING):
            pairs = classify_normalization_issue(normalization_warnings, spec_coverage if isinstance(spec_coverage, dict) else None)
            fd, ft = pairs[0] if pairs else ("normalization", "low_mapping_coverage")
            log_sync_event(
                "normalize",
                "warning",
                obs_mc.NORMALIZATION_LOW_COVERAGE,
                corr,
                metrics={"mapping_ratio": ratio_f, "threshold": float(settings.SPEC_MAPPING_MIN_COVERAGE_WARNING)},
                details=summ,
                failure_domain=fd,
                failure_type=ft,
            )

        normalized = NormalizedProduct(
            store=store,
            url=url,
            title=title,
            title_clean=title_clean,
            source_id=source_id,
            external_ids=external_ids,
            barcode=barcode,
            model_name=model_name,
            category_hint=category_hint,
            price_raw=price_raw,
            price_value=price_value,
            currency=(item.get("currency") or "UZS").strip(),
            in_stock=in_stock,
            brand=brand,
            raw_specs=raw_specs,
            typed_specs=typed_after_sanity,
            normalization_warnings=normalization_warnings,
            spec_coverage=spec_coverage,
            field_confidence=field_confidence,
            suppressed_typed_fields=suppressed_typed_fields,
            normalization_quality=quality_dict,
            description=description,
            image_urls=normalize_image_urls(item.get("image_urls")),
        )
        item["_normalized"] = normalized.model_dump(mode="json")

        if settings.DEV_MODE and settings.DEV_ENABLE_DEBUG_SUMMARIES:
            cap = 20 if settings.DEV_ENABLE_VERBOSE_STAGE_OUTPUT else 5
            NormalizePipeline._dev_debug_emit_count += 1
            if NormalizePipeline._dev_debug_emit_count <= cap:
                from application.dev.debug_summary import build_normalized_debug_view
                from infrastructure.observability.event_logger import log_developer_experience_event

                view = build_normalized_debug_view(item["_normalized"], settings)
                log_developer_experience_event(
                    obs_mc.DEV_DEBUG_SUMMARY_BUILT,
                    dev_run_mode=settings.DEV_RUN_MODE,
                    store_name=store,
                    sections_included=["normalized"],
                    items_count=1,
                    details={"preview": view},
                )
        return item
