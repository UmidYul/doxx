from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from infrastructure.pipelines.normalize_pipeline import NormalizePipeline

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "regression" / "normalization"


@pytest.mark.parametrize(
    "name",
    ["phone", "laptop", "tv", "appliance", "accessory"],
)
def test_normalization_regression_fixture_mapping(name: str):
    path = FIXTURES / f"{name}.json"
    spec = json.loads(path.read_text(encoding="utf-8"))
    item = dict(spec["raw_item"])
    NormalizePipeline().process_item(item, MagicMock(store_name=item.get("source", "mediapark")))
    n = item.get("_normalized")
    assert n is not None, name
    assert n["category_hint"] == spec.get("expected_category_hint", spec["category"])
    assert "raw_specs" in n and isinstance(n["raw_specs"], dict)
    assert "typed_specs" in n and isinstance(n["typed_specs"], dict)
    assert "normalization_warnings" in n
    assert "spec_coverage" in n and isinstance(n["spec_coverage"], dict)
    ratio = float(n["spec_coverage"].get("mapping_ratio") or 0.0)
    assert ratio >= float(spec["min_mapping_ratio"]), f"{name}: mapping_ratio {ratio} below baseline"
    for k in spec.get("expect_typed_keys") or []:
        assert k in n["typed_specs"], f"{name}: expected typed key {k!r} missing"

def test_barcode_from_raw_specs_and_external_ids_stable():
    """Barcode is derived from raw_specs (not top-level item); model_name from title/brand."""
    item = {
        "source": "mediapark",
        "url": "https://mediapark.uz/p/bc-1",
        "title": "Phone SM-G991",
        "source_id": "bc-1",
        "price_str": "1",
        "in_stock": True,
        "brand": "Samsung",
        "raw_specs": {"штрихкод": "8600123456789"},
        "image_urls": [],
    }
    NormalizePipeline().process_item(item, MagicMock(store_name="mediapark"))
    n = item["_normalized"]
    assert n.get("barcode") == "8600123456789"
    assert n.get("model_name")
    assert n.get("external_ids", {}).get("mediapark") == "bc-1"
