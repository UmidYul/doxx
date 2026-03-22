from __future__ import annotations

from collections import Counter
from typing import Any

from domain.typed_specs import TypedPartialSpecs


def calculate_mapping_ratio(raw_specs: dict[str, str], mapped_count: int) -> float:
    n = len([k for k, v in raw_specs.items() if str(k).strip() and str(v).strip()])
    if n == 0:
        return 1.0
    return min(1.0, max(0.0, mapped_count / n))


def summarize_unmapped_labels(unmapped_labels: list[str]) -> dict[str, int]:
    return dict(Counter(unmapped_labels))


def build_spec_coverage_report(
    raw_specs: dict[str, str],
    typed_specs: TypedPartialSpecs,
    meta: dict[str, Any],
) -> dict[str, Any]:
    compact = typed_specs.to_compact_dict()
    total = len([k for k, v in raw_specs.items() if str(k).strip() and str(v).strip()])
    mapped_count = int(meta.get("mapped_fields_count", 0))
    unmapped_count = int(meta.get("unmapped_fields_count", 0))
    ratio = calculate_mapping_ratio(raw_specs, mapped_count)
    deprecated = list(meta.get("deprecated_alias_hits", []) or [])
    conflicts = list(meta.get("conflicting_fields", []) or [])
    return {
        "total_raw_fields": total,
        "mapped_fields_count": mapped_count,
        "unmapped_fields_count": unmapped_count,
        "mapping_ratio": ratio,
        "unmapped_labels": list(meta.get("unmapped_labels", []) or []),
        "deprecated_alias_hits": deprecated,
        "conflict_count": len(conflicts),
        "conflicting_fields": conflicts,
        "typed_fields_filled": sorted(compact.keys()),
    }
