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


def test_blocked_product_url_not_marked_seen_and_can_retry_next_listing(monkeypatch: pytest.MonkeyPatch):
    spider = _FrameworkSpider()
    spider._crawl_registry_ref = None
    attempts = {"count": 0}

    def _schedule(url: str, *, response: scrapy.http.Response, meta: dict[str, Any]):
        attempts["count"] += 1
        if attempts["count"] == 1:
            return None
        return scrapy.Request(response.urljoin(url), meta=meta)

    monkeypatch.setattr(spider, "schedule_product_request", _schedule)

    r1 = _listing_response(
        "http://example.com/cat",
        meta={
            "inject_urls": ["http://example.com/p/1"],
            "inject_next": None,
            "page": 1,
        },
    )
    out1 = list(spider.parse_listing(r1))
    assert out1 == []

    r2 = _listing_response(
        "http://example.com/cat?page=2",
        meta={
            "inject_urls": ["http://example.com/p/1"],
            "inject_next": None,
            "page": 2,
        },
    )
    out2 = list(spider.parse_listing(r2))
    assert len(out2) == 1
    assert spider.crawl_registry.product_urls_deduped_total == 0


def test_blocked_product_urls_are_deferred_and_drained(monkeypatch: pytest.MonkeyPatch):
    spider = _FrameworkSpider()
    spider._crawl_registry_ref = None
    calls = {"count": 0}

    def _schedule_with_two_slots(url: str, *, response: scrapy.http.Response, meta: dict[str, Any]):
        calls["count"] += 1
        if calls["count"] > 2:
            return None
        return scrapy.Request(response.urljoin(url), meta=meta)

    monkeypatch.setattr(spider, "schedule_product_request", _schedule_with_two_slots)

    listing = _listing_response(
        "http://example.com/cat",
        meta={
            "inject_urls": [
                "http://example.com/p/1",
                "http://example.com/p/2",
                "http://example.com/p/3",
                "http://example.com/p/4",
            ],
            "inject_next": None,
            "page": 1,
        },
    )
    scheduled = list(spider.parse_listing(listing))

    assert [req.url for req in scheduled] == [
        "http://example.com/p/1",
        "http://example.com/p/2",
    ]
    pending, pending_seen = spider._pending_listing_product_queue()
    assert len(pending) == 2
    assert pending_seen == {"http://example.com/p/3", "http://example.com/p/4"}

    def _schedule_open(url: str, *, response: scrapy.http.Response, meta: dict[str, Any]):
        return scrapy.Request(response.urljoin(url), meta=meta)

    monkeypatch.setattr(spider, "schedule_product_request", _schedule_open)
    product_response = TextResponse(
        url="http://example.com/pdp/1",
        request=scrapy.Request("http://example.com/pdp/1"),
        body=b"{}",
        encoding="utf-8",
    )
    drained = list(spider._drain_pending_listing_products(product_response))

    assert [req.url for req in drained] == [
        "http://example.com/p/3",
        "http://example.com/p/4",
    ]
    assert len(pending) == 0
    assert pending_seen == set()


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


def test_common_next_page_finds_hidden_query_page_link():
    spider = _FrameworkSpider()
    response = _listing_response(
        "http://example.com/cat",
        meta={"inject_urls": [], "inject_next": None, "page": 1},
        body="""
        <html><body>
          <a style="display:none" href="/cat?page=2">2</a>
          <div>{}</div>
        </body></html>
        """.format("x" * 400),
    )

    assert (
        spider.extract_common_next_page_url(
            response,
            product_urls=[],
            min_product_links=99,
            path_markers=("/cat",),
        )
        == "http://example.com/cat?page=2"
    )


def test_common_next_page_synthesizes_query_page_and_preserves_filters():
    spider = _FrameworkSpider()
    response = _listing_response(
        "http://example.com/cat?brand=apple&sort=price",
        meta={"inject_urls": [], "inject_next": None, "page": 1},
    )

    assert (
        spider.extract_common_next_page_url(
            response,
            product_urls=["http://example.com/p/1", "http://example.com/p/2"],
            min_product_links=2,
            path_markers=("/cat",),
        )
        == "http://example.com/cat?brand=apple&sort=price&page=2"
    )


def test_common_next_page_respects_minimum_product_count():
    spider = _FrameworkSpider()
    response = _listing_response(
        "http://example.com/cat",
        meta={"inject_urls": [], "inject_next": None, "page": 1},
    )

    assert (
        spider.extract_common_next_page_url(
            response,
            product_urls=["http://example.com/p/1"],
            min_product_links=2,
            path_markers=("/cat",),
        )
        is None
    )


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


def test_targeting_normalizes_category_and_iphone_brand():
    spider = _FrameworkSpider()
    spider.category = "phones"
    spider.brand = "iPhone"

    assert spider._target_categories() == ("phone",)
    assert spider._target_brands() == ("apple",)
    assert spider.item_matches_targeting({"title": "iPhone 15 Pro", "category_hint": "phone", "brand": ""})
    assert not spider.item_matches_targeting({"title": "Samsung Galaxy S24", "category_hint": "phone", "brand": "Samsung"})


def test_target_start_category_urls_prefers_exact_brand_category_map():
    spider = _FrameworkSpider()
    spider.category_url_map = {"phone": ("http://example.com/phones",)}
    spider.brand_category_url_map = {("phone", "apple"): ("http://example.com/phones/apple",)}
    spider.category = "phone"
    spider.brand = "iPhone"

    assert spider.target_start_category_urls(("http://example.com/default",)) == ("http://example.com/phones/apple",)


def test_target_start_category_urls_prefers_explicit_category_url():
    spider = _FrameworkSpider()
    spider.category = "phone"
    spider.category_url = "http://example.com/custom"

    assert spider.target_start_category_urls(("http://example.com/default",)) == ("http://example.com/custom",)


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


def test_parse_listing_honeypot_filter_drops_hidden_product_urls():
    spider = _FrameworkSpider()
    spider._crawl_registry_ref = None

    def _schedule(url: str, *, response: scrapy.http.Response, meta: dict[str, Any]):
        return scrapy.Request(response.urljoin(url), meta=meta)

    spider.schedule_product_request = _schedule  # type: ignore[method-assign]

    r = _listing_response(
        "http://example.com/cat",
        meta={
            "inject_urls": [
                "http://example.com/p/trap",
                "http://example.com/p/live",
            ],
            "inject_next": None,
            "page": 1,
        },
        body="""
        <html><body>
          <a href="/p/trap" style="display:none">trap</a>
          <a href="/p/live">live</a>
          <!-- filler to avoid empty-shell heuristic -->
          <div>{}</div>
        </body></html>
        """.format("x" * 400),
    )

    with (
        patch.object(settings, "SCRAPY_HONEYPOT_FILTER_ENABLED", True),
        patch.object(settings, "SCRAPY_HONEYPOT_FILTER_MAX_FILTER_RATIO", 0.9),
        patch("infrastructure.spiders.honeypot_filter.is_feature_enabled", return_value=True),
    ):
        out = list(spider.parse_listing(r))

    urls = [req.url for req in out if isinstance(req, scrapy.Request)]
    assert "http://example.com/p/trap" not in urls
    assert "http://example.com/p/live" in urls


def test_parse_listing_honeypot_ratio_guard_preserves_links():
    spider = _FrameworkSpider()
    spider._crawl_registry_ref = None

    def _schedule(url: str, *, response: scrapy.http.Response, meta: dict[str, Any]):
        return scrapy.Request(response.urljoin(url), meta=meta)

    spider.schedule_product_request = _schedule  # type: ignore[method-assign]

    r = _listing_response(
        "http://example.com/cat",
        meta={
            "inject_urls": [
                "http://example.com/p/1",
                "http://example.com/p/2",
                "http://example.com/p/3",
            ],
            "inject_next": None,
            "page": 1,
        },
        body="""
        <html><body>
          <div hidden><a href="/p/1">1</a></div>
          <div hidden><a href="/p/2">2</a></div>
          <div hidden><a href="/p/3">3</a></div>
          <div>{}</div>
        </body></html>
        """.format("x" * 400),
    )

    with (
        patch.object(settings, "SCRAPY_HONEYPOT_FILTER_ENABLED", True),
        patch.object(settings, "SCRAPY_HONEYPOT_FILTER_MAX_FILTER_RATIO", 0.2),
        patch("infrastructure.spiders.honeypot_filter.is_feature_enabled", return_value=True),
    ):
        out = list(spider.parse_listing(r))

    urls = [req.url for req in out if isinstance(req, scrapy.Request)]
    assert len(urls) == 3
    assert "http://example.com/p/1" in urls
    assert "http://example.com/p/2" in urls
    assert "http://example.com/p/3" in urls
