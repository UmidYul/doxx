from __future__ import annotations

from typing import Any

from application.extractors import spec_warning_codes as WC
from application.extractors.spec_confidence import get_min_confidence_for_category
from config.settings import settings
from domain.normalization_quality import NormalizationQualitySummary
from domain.typed_specs import TypedPartialSpecs


def build_normalization_quality_summary(
    *,
    category_hint: str | None,
    field_confidence: dict[str, Any],
    suppressed_typed_fields: list[dict[str, Any]],
    conflicting_fields: list[str],
    normalization_warnings: list[str],
    mapping_ratio: float | None,
    typed_specs: TypedPartialSpecs,
) -> NormalizationQualitySummary:
    _ = field_confidence
    thr = get_min_confidence_for_category(category_hint)
    emitted = typed_specs.to_compact_dict()
    confident = 0
    for fname in emitted:
        fd = field_confidence.get(fname)
        if isinstance(fd, dict):
            try:
                if float(fd.get("confidence", 0)) >= thr:
                    confident += 1
            except (TypeError, ValueError):
                pass
        elif not settings.ENABLE_TYPED_SPEC_CONFIDENCE:
            confident += 1

    if confident == 0 and emitted:
        confident = len(emitted)

    supp_by_conf = sum(
        1
        for s in suppressed_typed_fields
        if isinstance(s, dict) and s.get("reason_code") == WC.SUPPRESSED_BY_CONFIDENCE
    )
    supp_by_conflict = sum(
        1
        for s in suppressed_typed_fields
        if isinstance(s, dict) and s.get("reason_code") == WC.SUPPRESSED_BY_CONFLICT
    )
    conflict_count = len(set(conflicting_fields)) + supp_by_conflict

    if not settings.ENABLE_NORMALIZATION_QUALITY_SUMMARY:
        return NormalizationQualitySummary()

    return NormalizationQualitySummary(
        mapping_ratio=mapping_ratio,
        confident_fields_count=confident,
        low_confidence_fields_count=supp_by_conf,
        suppressed_fields_count=len(suppressed_typed_fields),
        conflict_count=conflict_count,
        warning_count=len(normalization_warnings),
    )
