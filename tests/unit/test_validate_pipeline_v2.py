from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest
from scrapy.exceptions import DropItem

from infrastructure.pipelines.validate_pipeline import ValidatePipeline


def _spider():
    s = MagicMock()
    s.store_name = "mediapark"
    return s


def _valid_item(**overrides):
    base = {
        "title": "Phone",
        "url": "https://example.com/p",
        "source": "mediapark",
        "source_id": "1",
        "price_str": "10 000 сум",
        "in_stock": True,
        "raw_specs": {"ram": "8GB"},
        "image_urls": ["https://img/1.jpg"],
    }
    base.update(overrides)
    return base


def test_validate_drops_missing_title():
    pipe = ValidatePipeline()
    with pytest.raises(DropItem, match="Missing title"):
        pipe.process_item({"url": "https://x"}, _spider())


def test_validate_drops_missing_url():
    pipe = ValidatePipeline()
    with pytest.raises(DropItem, match="Missing URL"):
        pipe.process_item({"title": "Phone", "url": ""}, _spider())


def test_validate_drops_missing_source():
    pipe = ValidatePipeline()
    spider = MagicMock(spec=[])
    with pytest.raises(DropItem, match="Missing source/store"):
        pipe.process_item({"title": "Phone", "url": "https://x"}, spider)


def test_validate_passes_valid_item():
    pipe = ValidatePipeline()
    item = _valid_item()
    out = pipe.process_item(item, _spider())
    assert out is item
    assert out["in_stock"] is True


def test_validate_does_not_bool_coerce_string_in_stock():
    """Strings are normalized in NormalizePipeline via normalize_stock_value."""
    pipe = ValidatePipeline()
    item = _valid_item(in_stock="false")
    pipe.process_item(item, _spider())
    assert item["in_stock"] == "false"


def test_validate_does_not_bool_coerce_net_string():
    pipe = ValidatePipeline()
    item = _valid_item(in_stock="нет")
    pipe.process_item(item, _spider())
    assert item["in_stock"] == "нет"


def test_validate_coerces_raw_specs_non_dict():
    pipe = ValidatePipeline()
    item = _valid_item(raw_specs="not a dict")
    pipe.process_item(item, _spider())
    assert item["raw_specs"] == {}


def test_validate_coerces_image_urls_non_list():
    pipe = ValidatePipeline()
    item = _valid_item(image_urls="single_url")
    pipe.process_item(item, _spider())
    assert item["image_urls"] == []


def test_validate_warns_no_price(caplog: pytest.LogCaptureFixture):
    pipe = ValidatePipeline()
    caplog.set_level(logging.WARNING)
    item = _valid_item(price_str="")
    pipe.process_item(item, _spider())
    assert "[VALIDATE_WARN]" in caplog.text


def test_validate_uses_spider_store_name():
    pipe = ValidatePipeline()
    item = {"title": "Phone", "url": "https://x", "source_id": "1", "price_str": "10"}
    spider = MagicMock()
    spider.store_name = "uzum"
    pipe.process_item(item, spider)
    assert item["source"] == "uzum"
