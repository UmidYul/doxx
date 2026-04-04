from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import scrapy

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRAPY_SETTINGS = REPO_ROOT / "config" / "scrapy_settings.py"


def test_global_scrapy_settings_do_not_register_playwright_handlers():
    text = SCRAPY_SETTINGS.read_text(encoding="utf-8")
    assert "ScrapyPlaywrightDownloadHandler" not in text
    assert "scrapy_playwright" not in text


def test_mediapark_registers_optional_playwright_handlers_for_ban_escalation():
    from infrastructure.spiders.mediapark import MediaparkSpider

    handlers = MediaparkSpider.custom_settings["DOWNLOAD_HANDLERS"]
    assert handlers["https"] == handlers["http"]
    assert handlers["https"].endswith("ScrapyPlaywrightDownloadHandler")


def test_uzum_registers_playwright_handlers_only_on_spider():
    from infrastructure.spiders.uzum import UzumSpider

    handlers = UzumSpider.custom_settings["DOWNLOAD_HANDLERS"]
    assert handlers["https"] == handlers["http"]
    assert handlers["https"].endswith("ScrapyPlaywrightDownloadHandler")


def test_uzum_start_request_uses_playwright_meta(monkeypatch: pytest.MonkeyPatch):
    from infrastructure.spiders.uzum import UzumSpider
    from config.settings import settings

    spider = UzumSpider()
    monkeypatch.setattr(settings, "ENABLE_RESOURCE_GOVERNANCE", False)

    class _S:
        def get(self, key, default=None):
            if key == "DOWNLOAD_HANDLERS":
                return UzumSpider.custom_settings.get("DOWNLOAD_HANDLERS")
            return default

    spider.settings = _S()
    reqs = list(spider.start_requests())
    assert len(reqs) >= 1
    assert all(r.meta.get("access_mode_selected") in {"browser", "plain"} for r in reqs)
    assert any("/category/smartfony-12690" in r.url for r in reqs)


def test_uzum_listing_request_injects_snapshot_anchors(monkeypatch: pytest.MonkeyPatch):
    from infrastructure.spiders.uzum import UzumSpider
    from config.settings import settings

    spider = UzumSpider()
    monkeypatch.setattr(settings, "ENABLE_RESOURCE_GOVERNANCE", False)

    class _S:
        def get(self, key, default=None):
            if key == "DOWNLOAD_HANDLERS":
                return UzumSpider.custom_settings.get("DOWNLOAD_HANDLERS")
            return default

    spider.settings = _S()
    req = list(spider.start_requests())[0]
    methods = req.meta["playwright_page_methods"]
    evaluate_args = [m.args[0] for m in methods if getattr(m, "method", "") == "evaluate"]

    assert any("__scrapy_snapshot__" in arg for arg in evaluate_args)
    assert all("wait_for_selector" not in getattr(m, "method", "") for m in methods)


def test_uzum_product_requests_stay_plain_http_by_default():
    from infrastructure.spiders.uzum import UzumSpider

    spider = UzumSpider()

    class _S:
        def get(self, key, default=None):
            if key == "DOWNLOAD_HANDLERS":
                return UzumSpider.custom_settings.get("DOWNLOAD_HANDLERS")
            return default

    spider.settings = _S()
    listing = scrapy.http.HtmlResponse(
        url="https://uzum.uz/ru/category/smartfony-12690",
        request=scrapy.Request("https://uzum.uz/ru/category/smartfony-12690"),
        body=b"<html></html>",
    )
    req = spider.schedule_product_request(
        "https://uzum.uz/ru/product/demo-phone-111111?skuId=123456",
        response=listing,
        meta={
            "category_url": listing.url,
            "page": 1,
            "force_browser": True,
            "playwright": True,
            "playwright_page_methods": ["should be stripped"],
        },
    )
    assert req is not None
    assert req.meta.get("playwright") is None
    assert req.meta.get("access_mode_selected") == "plain"
    assert req.meta.get("force_browser") is None
    assert req.priority == 20
    assert req.dont_filter is True


def test_uzum_duplicate_listing_signature_ignores_page_number():
    from infrastructure.spiders.uzum import UzumSpider

    spider = UzumSpider()
    urls = [
        "https://uzum.uz/ru/product/demo-phone-111111?skuId=123456",
        "https://uzum.uz/ru/product/demo-phone-222222?skuId=234567",
    ]
    r1 = scrapy.http.HtmlResponse(
        url="https://uzum.uz/ru/category/smartfony-12690?page=1",
        request=scrapy.Request("https://uzum.uz/ru/category/smartfony-12690?page=1"),
        body=b"<html></html>",
    )
    r2 = scrapy.http.HtmlResponse(
        url="https://uzum.uz/ru/category/smartfony-12690?page=2",
        request=scrapy.Request("https://uzum.uz/ru/category/smartfony-12690?page=2"),
        body=b"<html></html>",
    )
    assert spider.build_listing_signature(r1, urls, 1) == spider.build_listing_signature(r2, urls, 2)


@pytest.mark.skipif(
    importlib.util.find_spec("scrapy_playwright") is None,
    reason="scrapy-playwright optional extra not installed",
)
def test_scrapy_playwright_handler_importable_when_extra_installed():
    import importlib

    importlib.import_module("scrapy_playwright.handler")
