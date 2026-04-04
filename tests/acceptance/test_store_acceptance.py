from __future__ import annotations

from pathlib import Path

import pytest
import scrapy.http

from application.qa.run_store_acceptance import run_acceptance_for_store
from infrastructure.spiders import edge_cases
from infrastructure.spiders.field_policy import is_usable_product_item
from infrastructure.spiders.mediapark import MediaparkSpider
from infrastructure.spiders.store_acceptance import (
    ALIFSHOP_ACCEPTANCE,
    MEDIAPARK_ACCEPTANCE,
    TEXNOMART_ACCEPTANCE,
    UZUM_ACCEPTANCE,
    get_store_acceptance_profile,
)

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


def test_texnomart_profile_tracks_browser_fallback_risks():
    p = get_store_acceptance_profile("texnomart")
    assert p.browser_dependence == "medium"
    assert p.max_duplicate_listing_repeats == TEXNOMART_ACCEPTANCE.max_duplicate_listing_repeats


def test_uzum_listing_extracts_unique_product_urls():
    from infrastructure.spiders.uzum import UzumSpider

    spider = UzumSpider()
    html = b"""
    <html><body>
      <a href="/ru/product/demo-phone-111111?skuId=222">one</a>
      <a href="/ru/product/demo-phone-111111?skuId=222">dup</a>
      <a href="https://uzum.uz/ru/product/demo-tv-333333?skuId=444">two</a>
      <a href="https://example.com/product/not-uzum">bad</a>
    </body></html>
    """
    resp = scrapy.http.HtmlResponse(url="https://uzum.uz/ru/category/smartfony-12690", body=html)
    urls = spider.extract_listing_product_urls(resp)
    assert len(urls) == 2
    assert all("uzum.uz" in u for u in urls)


def test_uzum_listing_extracts_nested_category_urls():
    from infrastructure.spiders.uzum import UzumSpider

    spider = UzumSpider()
    html = b"""
    <html><body>
      <a href="/ru/category/smartfony-12690">phones</a>
      <a href="/ru/category/smartfony-samsung-18195">samsung phones</a>
      <a href="/ru/category/smartfony-i-telefony-10044">zero result branch</a>
      <a href="/ru/category/knopochnye-telefony-14262">feature phones</a>
      <a href="/ru/product/demo-phone-111111?skuId=222">product</a>
      <a href="https://example.com/ru/category/bad">external</a>
    </body></html>
    """
    resp = scrapy.http.HtmlResponse(url="https://uzum.uz/ru/category/smartfony-12690", body=html)
    categories = spider.extract_listing_category_urls(resp)
    # Only high-value smartphone branches survive; zero-result / low-value phone branches are skipped.
    assert len(categories) == 1
    assert categories[0] == "/ru/category/smartfony-samsung-18195"


def test_uzum_pdp_json_ld_parsing_smoke():
    from infrastructure.spiders.uzum import UzumSpider

    spider = UzumSpider()
    body = b"""
    <html><head>
      <script type="application/ld+json">
      {
        "@context":"https://schema.org",
        "@graph":[
          {
            "@type":"ProductGroup",
            "productGroupID":"111111",
            "name":"Demo Phone X",
            "description":"Demo description",
            "image":["https://images.uzum.uz/demo-group.jpg"],
            "hasVariant":[
              {
                "@type":"Product",
                "name":"Demo Phone X",
                "sku":"123456",
                "url":"https://uzum.uz/ru/product/demo-phone-111111?skuId=123456",
                "offers":{"@type":"Offer","price":"4990000","availability":"https://schema.org/InStock"},
                "brand":{"@type":"Brand","name":"DemoBrand"},
                "additionalProperty":[
                  {"name":"Color","value":"Black"},
                  {"name":"Storage","value":"256 GB"}
                ],
                "image":["https://images.uzum.uz/demo.jpg"]
              }
            ]
          }
        ]
      }
      </script>
    </head><body><h1>Demo Phone X</h1></body></html>
    """
    url = "https://uzum.uz/ru/product/demo-phone-111111?skuId=123456"
    resp = scrapy.http.HtmlResponse(url=url, body=body)
    raw = spider.full_parse_item(resp)
    assert raw is not None
    assert raw["source_id"] == "sku:123456"
    assert raw["title"] == "Demo Phone X"
    assert raw["in_stock"] is True
    assert raw["raw_specs"]["Color"] == "Black"
    assert raw["raw_specs"]["Storage"] == "256 GB"
    assert raw["image_urls"]
    assert raw["category_hint"] in UZUM_ACCEPTANCE.expected_category_hints


def test_texnomart_listing_extracts_unique_product_urls():
    from infrastructure.spiders.texnomart import TexnomartSpider

    spider = TexnomartSpider()
    html = b"""
    <html><body>
      <a href="/ru/product/demo-phone-111111?sku=222">one</a>
      <a href="/ru/product/demo-phone-111111?sku=222">dup</a>
      <a href="https://texnomart.uz/ru/catalog/product/demo-tv-333333">two</a>
      <a href="https://example.com/product/not-texnomart">bad</a>
    </body></html>
    """
    resp = scrapy.http.HtmlResponse(url="https://texnomart.uz/ru/catalog/smartfony", body=html)
    urls = spider.extract_listing_product_urls(resp)
    assert len(urls) == 2
    assert all("texnomart.uz" in u for u in urls)


def test_texnomart_listing_extracts_nested_category_urls():
    from infrastructure.spiders.texnomart import TexnomartSpider

    spider = TexnomartSpider()
    html = b"""
    <html><body>
      <a href="/ru/katalog/smartfony/samsung">Samsung category</a>
      <a href="/ru/katalog/telefony">Phones category</a>
      <a href="/ru/product/demo-phone-111111">Product should be ignored</a>
      <a href="https://example.com/ru/katalog/bad">External should be ignored</a>
    </body></html>
    """
    resp = scrapy.http.HtmlResponse(url="https://texnomart.uz/ru/katalog/smartfony", body=html)
    categories = spider.extract_listing_category_urls(resp)
    assert len(categories) == 2
    assert all(c.startswith("/ru/") for c in categories)


def test_texnomart_listing_synthesizes_next_page_for_katalog_paths():
    from infrastructure.spiders.texnomart import TexnomartSpider

    spider = TexnomartSpider()
    html = b"""
    <html><body>
      <a href="/ru/product/detail/111111/">one</a>
      <a href="/ru/product/detail/222222/">two</a>
    </body></html>
    """
    resp = scrapy.http.HtmlResponse(url="https://texnomart.uz/ru/katalog/smartfony/", body=html)
    assert spider.extract_next_page_url(resp) == "https://texnomart.uz/ru/katalog/smartfony/?page=2"


def test_texnomart_pdp_json_ld_parsing_smoke():
    from infrastructure.spiders.texnomart import TexnomartSpider

    spider = TexnomartSpider()
    body = b"""
    <html><head>
      <script type="application/ld+json">
      {
        "@context":"https://schema.org",
        "@graph":[{
          "@type":"Product",
          "name":"Demo TV 55",
          "sku":"555666",
          "description":"Demo description",
          "offers":{"@type":"Offer","price":"7990000","availability":"https://schema.org/InStock"},
          "brand":{"@type":"Brand","name":"DemoBrand"},
          "additionalProperty":[{"name":"Diagonal","value":"55"}],
          "image":["https://cdn.texnomart.uz/demo.jpg"]
        }]
      }
      </script>
    </head><body><h1>Demo TV 55</h1></body></html>
    """
    url = "https://texnomart.uz/ru/product/demo-tv-333333?sku=555666"
    resp = scrapy.http.HtmlResponse(url=url, body=body)
    raw = spider.full_parse_item(resp)
    assert raw is not None
    assert raw["source_id"] == "sku:555666"
    assert raw["title"] == "Demo TV 55"
    assert raw["in_stock"] is True
    assert raw["source"] == "texnomart"
    assert raw["category_hint"] == "tv"


def test_alifshop_listing_extracts_unique_product_urls():
    from infrastructure.spiders.alifshop import AlifshopSpider

    spider = AlifshopSpider()
    html = b"""
    <html><body>
      <a href="/ru/moderated-offer/demo-phone-1772002920">one</a>
      <a href="/ru/moderated-offer/demo-phone-1772002920">dup</a>
      <a href="/ru/moderated-offer/demo-phone-1772002921">two</a>
      <a href="https://example.com/ru/moderated-offer/bad">bad</a>
    </body></html>
    """
    resp = scrapy.http.HtmlResponse(url="https://alifshop.uz/ru/categories/smartfoni-apple", body=html)
    urls = spider.extract_listing_product_urls(resp)
    assert len(urls) == 2
    assert all("alifshop.uz" in u for u in urls)


def test_alifshop_listing_extracts_nested_category_urls():
    from infrastructure.spiders.alifshop import AlifshopSpider

    spider = AlifshopSpider()
    html = b"""
    <html><body>
      <a href="/ru/categories/smartfoni-samsung">phones</a>
      <a href="/ru/categories/televizory">other electronics</a>
      <a href="/ru/moderated-offer/demo-phone-1772002920">product</a>
      <a href="https://example.com/ru/categories/bad">external</a>
    </body></html>
    """
    resp = scrapy.http.HtmlResponse(url="https://alifshop.uz/ru/categories/smartfoni-apple", body=html)
    categories = spider.extract_listing_category_urls(resp)
    assert len(categories) == 1
    assert categories[0] == "/ru/categories/smartfoni-samsung"


def test_alifshop_pdp_meta_and_specs_parsing_smoke():
    from infrastructure.spiders.alifshop import AlifshopSpider

    spider = AlifshopSpider()
    body = b"""
    <html><head>
      <title>SMARTUP - Buy Demo Phone Blue online</title>
      <meta property="product:price:amount" content="10999000" />
      <meta property="product:availability" content="in stock" />
      <meta property="og:image" content="https://s3.fortifai.uz/shop/moderation/demo-phone-blue.jpg" />
      <meta name="description" content="Demo Phone Blue in alifshop" />
    </head><body>
      <h1>Demo Phone Blue</h1>
      <div class="border-b-[0.5px] border-light-surface-300 py-2">
        <div class="flex md:gap-4 gap-3">
          <p class="w-full text-sm md:text-md text-light-basic-300 max-w-[320px]">Color</p>
          <div class="text-sm md:text-md w-full whitespace-break-spaces"><span>Deep Blue</span></div>
        </div>
      </div>
      <div class="border-b-[0.5px] border-light-surface-300 py-2">
        <div class="flex md:gap-4 gap-3">
          <p class="w-full text-sm md:text-md text-light-basic-300 max-w-[320px]">Storage</p>
          <div class="text-sm md:text-md w-full whitespace-break-spaces"><span>256 GB</span></div>
        </div>
      </div>
    </body></html>
    """
    url = "https://alifshop.uz/ru/moderated-offer/demo-phone-blue-1772002920"
    resp = scrapy.http.HtmlResponse(url=url, body=body)
    raw = spider.full_parse_item(resp)
    assert raw is not None
    assert raw["source_id"] == "1772002920"
    assert raw["title"] == "Demo Phone Blue"
    assert raw["in_stock"] is True
    assert raw["image_urls"] == ["https://s3.fortifai.uz/shop/moderation/demo-phone-blue.jpg"]
    assert raw["raw_specs"]["Color"] == "Deep Blue"
    assert raw["category_hint"] == "phone"
    assert raw["source"] == "alifshop"


def test_alifshop_profile_reflects_http_only_store():
    p = get_store_acceptance_profile("alifshop")
    assert p.browser_dependence == "low"
    assert p.supports_variants is False
    assert p.min_product_links_per_listing_page == ALIFSHOP_ACCEPTANCE.min_product_links_per_listing_page


@pytest.mark.parametrize("store", ["mediapark", "texnomart", "uzum", "alifshop"])
def test_fixture_runner_smoke(store: str):
    report, summary = run_acceptance_for_store(store)
    assert "quality_gate_passed" in report
    assert summary["store"] == store
