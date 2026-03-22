from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
import scrapy
import scrapy.http
from scrapy.http import TextResponse

from config.settings import settings
from infrastructure.spiders.base import BaseProductSpider


@pytest.fixture(autouse=True)
def _network_open_for_synthetic_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    """example.com / test doubles are not in ALLOWED_STORE_HOSTS — use open mode for framework tests."""
    monkeypatch.setattr(settings, "NETWORK_SECURITY_MODE", "open")


class _FrameworkSpider(BaseProductSpider):
    """Test double: listing URLs and next page come from response.meta."""

    name = "framework_test"
    store_name = "teststore"

    def start_category_urls(self) -> tuple[str, ...]:
        return ("http://example.com/cat",)

    def is_product_page(self, response: scrapy.http.Response) -> bool:
        return "/pdp/" in response.url

    def extract_listing_product_urls(self, response: scrapy.http.Response) -> list[str]:
        return list(response.meta.get("inject_urls", []))

    def extract_next_page_url(self, response: scrapy.http.Response) -> str | None:
        return response.meta.get("inject_next")

    def extract_source_id_from_url(self, url: str) -> str | None:
        # Test helper: id only when /p/ segment exists (mimics SKU-in-path stores).
        if "/p/" not in url:
            return None
        return url.rstrip("/").rsplit("/", 1)[-1] or None

    def full_parse_item(self, response: scrapy.http.Response) -> dict[str, Any] | None:
        return None


def _listing_response(
    url: str,
    *,
    meta: dict[str, Any],
    body: str | None = None,
) -> TextResponse:
    if body is None:
        # Avoid false ``empty_shell`` ban heuristics on tiny bodies (access profile threshold).
        body = "<html><body>" + ("x" * 400) + "</body></html>"
    m = {
        "category_url": "http://example.com/cat",
        "page": 1,
        "empty_streak": 0,
        "dup_sig_streak": 0,
        **meta,
    }
    req = scrapy.Request(url, meta=m)
    return TextResponse(url=url, request=req, body=body.encode(), encoding="utf-8")


def test_duplicate_product_urls_not_scheduled_twice():
    spider = _FrameworkSpider()
    spider._crawl_registry_ref = None
    r = _listing_response(
        "http://example.com/cat",
        meta={
            "inject_urls": [
                "http://example.com/p/onlydup",
                "http://example.com/p/onlydup",
            ],
            "inject_next": None,
            "page": 1,
        },
    )
    out = list(spider.parse_listing(r))
    assert len(out) == 1
    assert spider.crawl_registry.product_urls_deduped_total == 1


def test_duplicate_source_id_second_url_skipped():
    spider = _FrameworkSpider()
    spider._crawl_registry_ref = None
    r = _listing_response(
        "http://example.com/cat",
        meta={
            "inject_urls": [
                "http://example.com/a/p/1",
                "http://example.com/b/p/1",
            ],
            "inject_next": None,
            "page": 1,
        },
    )
    out = list(spider.parse_listing(r))
    assert len(out) == 1
    assert spider.crawl_registry.product_urls_deduped_total == 1


def test_should_stop_pagination_empty_repeats():
    spider = _FrameworkSpider()
    with (
        patch.object(settings, "SCRAPY_MAX_EMPTY_LISTING_REPEATS", 3),
        patch.object(settings, "SCRAPY_MAX_PAGES_PER_CATEGORY", 99),
        patch.object(settings, "SCRAPY_MAX_DUPLICATE_LISTING_REPEATS", 99),
    ):
        stop, reason = spider.should_stop_pagination(
            next_url="http://x/next",
            page=1,
            empty_streak=5,
            dup_sig_streak=0,
        )
    assert stop and reason == "empty_repeats"


def test_should_stop_duplicate_listing_sig_streak():
    spider = _FrameworkSpider()
    with (
        patch.object(settings, "SCRAPY_MAX_EMPTY_LISTING_REPEATS", 99),
        patch.object(settings, "SCRAPY_MAX_PAGES_PER_CATEGORY", 99),
        patch.object(settings, "SCRAPY_MAX_DUPLICATE_LISTING_REPEATS", 2),
    ):
        stop, reason = spider.should_stop_pagination(
            next_url="http://x",
            page=1,
            empty_streak=0,
            dup_sig_streak=2,
        )
    assert stop and reason == "duplicate_listing_repeats"


def test_pagination_stops_on_revisited_listing_url():
    from infrastructure.spiders import url_tools

    spider = _FrameworkSpider()
    spider._crawl_registry_ref = None
    reg = spider.crawl_registry
    reg.remember_listing_page_url(url_tools.canonicalize_url("http://example.com/cat?page=2"))
    r = _listing_response(
        "http://example.com/cat?page=1",
        meta={
            "inject_urls": ["http://example.com/p/a"],
            "inject_next": "http://example.com/cat?page=2",
            "page": 1,
        },
    )
    out = list(spider.parse_listing(r))
    next_reqs = [x for x in out if isinstance(x, scrapy.Request)]
    assert not any("page=2" in x.url for x in next_reqs)


def test_apply_soft_product_partial_without_price():
    spider = _FrameworkSpider()
    resp = TextResponse(
        url="http://example.com/pdp/x",
        request=scrapy.Request("http://example.com/pdp/x"),
        body=b"{}",
        encoding="utf-8",
    )
    raw = {
        "title": "Phone",
        "source_id": "9",
        "price_str": "",
        "image_urls": ["http://i/img.jpg"],
    }
    item, status = spider.apply_soft_product_policy(raw, resp)
    assert status == "partial"
    assert item is not None
    assert item["title"] == "Phone"


def test_apply_soft_product_drop_without_title_or_id():
    spider = _FrameworkSpider()
    resp = TextResponse(
        url="http://example.com/catalog/widget",
        request=scrapy.Request("http://example.com/catalog/widget"),
        body=b"{}",
        encoding="utf-8",
    )
    raw = {"title": "", "price_str": "100", "image_urls": []}
    item, status = spider.apply_soft_product_policy(raw, resp)
    assert item is None
    assert status == "drop"


def test_listing_duplicate_signature_increments_streak():
    spider = _FrameworkSpider()
    spider._crawl_registry_ref = None
    shared = {"inject_urls": ["http://example.com/p/onlyone"], "inject_next": None, "page": 1}
    r1 = _listing_response("http://example.com/cat", meta=dict(shared))
    list(spider.parse_listing(r1))
    r2 = _listing_response(
        "http://example.com/cat?junk=1",
        meta=dict(shared),
    )
    list(spider.parse_listing(r2))
    assert spider.crawl_registry.listing_pages_duplicated_total >= 1
