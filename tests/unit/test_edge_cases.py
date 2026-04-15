from __future__ import annotations

import scrapy.http

from infrastructure.spiders import edge_cases


def test_listing_repeat_and_duplicate_pdp_urls():
    urls = [
        "https://shop.uz/p/1",
        "https://shop.uz/p/1",
        "https://shop.uz/p/2",
    ]
    resp = scrapy.http.HtmlResponse(
        url="https://shop.uz/cat",
        body=(b"<html><body>" + b"x" * 500 + b"</body></html>"),
    )
    tags = edge_cases.classify_listing_edge_case(
        resp,
        urls,
        empty_body_threshold=256,
        listing_signature_duplicate=True,
    )
    assert edge_cases.EDGE_LISTING_REPEAT in tags
    assert edge_cases.EDGE_DUPLICATE_PDP_URLS in tags


def test_listing_without_pdp_when_no_urls():
    resp = scrapy.http.HtmlResponse(url="https://shop.uz/e", body=b"<html>x" * 200 + b"</html>")
    tags = edge_cases.classify_listing_edge_case(resp, [], empty_body_threshold=256)
    assert edge_cases.EDGE_LISTING_WITHOUT_PDP in tags


def test_deleted_and_soft_404_product():
    item = {"title": "t", "url": "https://x/p/1", "source": "s", "source_id": "1", "price_str": "1"}
    r404 = scrapy.http.HtmlResponse(url=item["url"], status=404, body=b"gone")
    assert edge_cases.EDGE_DELETED_PRODUCT_404 in edge_cases.classify_product_edge_case(item, r404)

    soft = scrapy.http.HtmlResponse(
        url=item["url"],
        status=200,
        body=b"<html><body>404 not found page</body></html>",
    )
    assert edge_cases.EDGE_PRODUCT_SOFT_404 in edge_cases.classify_product_edge_case(item, soft)


def test_soft_404_detection_ignores_script_noise_and_asset_uuids():
    item = {"title": "Demo Phone", "url": "https://x/p/1", "source": "s", "source_id": "1", "price_str": "10999000"}
    response = scrapy.http.HtmlResponse(
        url=item["url"],
        status=200,
        body="""
        <html>
          <head>
            <script>window.__noise = "404 not found";</script>
          </head>
          <body>
            <h1>Demo Phone</h1>
            <img src="https://cdn.example.com/demo-4045-asset.webp" />
            <p>Valid PDP body content</p>
          </body>
        </html>
        """.encode("utf-8"),
        encoding="utf-8",
    )

    tags = edge_cases.classify_product_edge_case(item, response)

    assert edge_cases.EDGE_PRODUCT_SOFT_404 not in tags


def test_missing_price_tag_not_always_fatal_for_usable():
    item = {"title": "t", "url": "https://x", "source": "s", "source_id": "1", "price_str": ""}
    ok = scrapy.http.HtmlResponse(url=item["url"], status=200, body=b"<html>ok</html>")
    tags = edge_cases.classify_product_edge_case(item, ok)
    assert edge_cases.EDGE_MISSING_PRICE in tags
