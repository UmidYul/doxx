from __future__ import annotations

from unittest.mock import MagicMock

from domain.normalized_product import NormalizedProduct
from domain.raw_product import RawProduct
from infrastructure.pipelines.normalize_pipeline import NormalizePipeline


def test_normalize_pipeline_raw_product_to_json_shape():
    raw = RawProduct(
        source="mediapark",
        url="https://example.com/p",
        source_id="1",
        title="Phone",
        price_str="1 234 000 сум",
        in_stock=True,
        raw_specs={"ram_gb": "8"},
        image_urls=[],
        description="",
    )
    pipe = NormalizePipeline()
    item = raw.model_dump()
    out = pipe.process_item(item, MagicMock(store_name="mediapark"))
    assert out is item
    norm = item["_normalized"]
    NormalizedProduct.model_validate(norm)
    assert norm["title"] == "Phone"
    assert norm["price_raw"] == "1 234 000 сум"
    assert norm["price"] == 1234000.0
    assert norm["currency"] == "UZS"
    assert norm["in_stock"] is True
    assert norm["raw_specs"] == {"ram_gb": "8"}


def test_normalize_pipeline_optional_price():
    raw = RawProduct(
        source="s",
        url="https://x",
        source_id="",
        title="T",
        price_str="",
        in_stock=False,
    )
    pipe = NormalizePipeline()
    item = raw.model_dump()
    pipe.process_item(item, MagicMock(store_name="s"))
    assert item["_normalized"]["price"] is None
    assert item["_normalized"]["in_stock"] is False
