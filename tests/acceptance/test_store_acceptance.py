from __future__ import annotations

from pathlib import Path

import pytest
import scrapy.http

from application.qa.run_store_acceptance import run_acceptance_for_store
from infrastructure.spiders import edge_cases
from infrastructure.spiders.field_policy import is_usable_product_item
from infrastructure.spiders.mediapark import MediaparkSpider
from infrastructure.spiders.store_acceptance import MEDIAPARK_ACCEPTANCE, UZUM_ACCEPTANCE, get_store_acceptance_profile

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "stores"


def _read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_mediapark_listing_yields_product_urls():
    spider = MediaparkSpider()
    resp = scrapy.http.HtmlResponse(
        url="https://mediapark.uz/products/category/telefony-17/smartfony-40?page=1",
        body=_read("mediapark/listing_good.html"),
    )
    urls = spider.extract_listing_product_urls(resp)
    assert len(urls) >= MEDIAPARK_ACCEPTANCE.min_product_links_per_listing_page


def test_mediapark_pdp_partial_is_usable_and_category_in_hints():
    spider = MediaparkSpider()
    url = "https://mediapark.uz/products/view/test-laptop-888"
    resp = scrapy.http.HtmlResponse(url=url, body=_read("mediapark/pdp_partial.html"))
    raw = spider.full_parse_item(resp)
    assert raw is not None
    raw.setdefault("source", spider.store_name)
    assert is_usable_product_item(raw)
    hint = raw.get("category_hint")
    assert hint in MEDIAPARK_ACCEPTANCE.expected_category_hints


def test_mediapark_acceptance_profile_passes_fixture_runner():
    report, _summary = run_acceptance_for_store("mediapark")
    assert report["quality_gate_passed"] is True


def test_uzum_empty_shell_classified():
    from infrastructure.access.store_profiles import get_store_profile

    resp = scrapy.http.HtmlResponse(url="https://uzum.uz/", body=_read("uzum/empty_shell.html"))
    access = get_store_profile("uzum")
    tags = edge_cases.classify_listing_edge_case(resp, [], empty_body_threshold=access.empty_body_threshold)
    assert edge_cases.EDGE_EMPTY_LISTING_SHELL in tags or edge_cases.EDGE_LISTING_WITHOUT_PDP in tags


def test_uzum_profile_expects_browser_shell_risks():
    p = get_store_acceptance_profile("uzum")
    assert p.supports_js_shell == "high"
    assert p.browser_dependence == "high"
    assert p.empty_shell_risk == "high"


@pytest.mark.parametrize("store", ["mediapark", "uzum"])
def test_fixture_runner_smoke(store: str):
    report, summary = run_acceptance_for_store(store)
    assert "quality_gate_passed" in report
    assert summary["store"] == store
