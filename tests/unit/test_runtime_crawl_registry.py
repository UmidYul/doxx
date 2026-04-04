from __future__ import annotations

from unittest.mock import patch

import pytest

from infrastructure.spiders.runtime_crawl_registry import CrawlRuntimeRegistry


@pytest.fixture
def reg() -> CrawlRuntimeRegistry:
    return CrawlRuntimeRegistry(store="mediapark")


def test_product_url_roundtrip(reg: CrawlRuntimeRegistry) -> None:
    assert not reg.has_product_url("https://x.uz/a")
    reg.remember_product_url("https://x.uz/a")
    assert reg.has_product_url("https://x.uz/a")


def test_source_id_scoped_by_store(reg: CrawlRuntimeRegistry) -> None:
    reg.remember_source_id("42")
    assert reg.has_source_id("42")
    assert not CrawlRuntimeRegistry(store="other").has_source_id("42")


def test_listing_signature(reg: CrawlRuntimeRegistry) -> None:
    sig = "abc123"
    assert not reg.has_listing_signature(sig)
    reg.remember_listing_signature(sig)
    assert reg.has_listing_signature(sig)


def test_snapshot_metrics(reg: CrawlRuntimeRegistry) -> None:
    reg.categories_started_total = 2
    reg.record_category_with_results("https://mediapark.uz/products/category/phones")
    reg.listing_cards_seen_total = 12
    reg.note_pagination_depth(3)
    reg.product_urls_deduped_total = 5
    reg.note_product_asset_coverage(has_specs=True, has_images=False)
    snap = reg.snapshot_metrics()
    assert snap["store"] == "mediapark"
    assert snap["categories_seeded_total"] == 2
    assert snap["categories_with_results_total"] == 1
    assert snap["listing_cards_seen_total"] == 12
    assert snap["pagination_depth_max"] == 3
    assert snap["categories_started_total"] == 2
    assert snap["product_urls_deduped_total"] == 5
    assert snap["products_with_specs_total"] == 1
    assert snap["products_without_images_total"] == 1


def test_trim_entries() -> None:
    r = CrawlRuntimeRegistry(store="t")
    with patch("infrastructure.spiders.runtime_crawl_registry.settings") as s:
        s.SCRAPY_CRAWL_REGISTRY_MAX_ENTRIES = 2
        r.remember_product_url("a")
        r.remember_product_url("b")
        r.remember_product_url("c")
    assert not r.has_product_url("a")
    assert r.has_product_url("c")
