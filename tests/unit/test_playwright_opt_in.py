from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRAPY_SETTINGS = REPO_ROOT / "config" / "scrapy_settings.py"


def test_global_scrapy_settings_do_not_register_playwright_handlers():
    text = SCRAPY_SETTINGS.read_text(encoding="utf-8")
    assert "ScrapyPlaywrightDownloadHandler" not in text
    assert "scrapy_playwright" not in text


def test_mediapark_has_no_playwright_download_handlers():
    from infrastructure.spiders.mediapark import MediaparkSpider

    assert "DOWNLOAD_HANDLERS" not in MediaparkSpider.custom_settings


def test_uzum_registers_playwright_handlers_only_on_spider():
    from infrastructure.spiders.uzum import UzumSpider

    handlers = UzumSpider.custom_settings["DOWNLOAD_HANDLERS"]
    assert handlers["https"] == handlers["http"]
    assert handlers["https"].endswith("ScrapyPlaywrightDownloadHandler")


def test_uzum_start_request_uses_playwright_meta():
    from infrastructure.spiders.uzum import UzumSpider

    spider = UzumSpider()
    reqs = list(spider.start_requests())
    assert len(reqs) == 1
    assert reqs[0].meta.get("playwright") is True


@pytest.mark.skipif(
    importlib.util.find_spec("scrapy_playwright") is None,
    reason="scrapy-playwright optional extra not installed",
)
def test_scrapy_playwright_handler_importable_when_extra_installed():
    import importlib

    importlib.import_module("scrapy_playwright.handler")
