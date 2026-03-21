from __future__ import annotations

import sys
from pathlib import Path
from subprocess import run

from config import scrapy_settings

_EXPECTED_PIPELINES = {
    "infrastructure.pipelines.validate_pipeline.ValidatePipeline": 100,
    "infrastructure.pipelines.normalize_pipeline.NormalizePipeline": 200,
    "infrastructure.pipelines.publish_pipeline.PublishPipeline": 300,
}

_REQUIRED_MIDDLEWARE_SUBSTRINGS = (
    "stealth_middleware.StealthMiddleware",
    "ratelimit_middleware.AdaptiveRateLimitMiddleware",
    "retry_middleware.ExponentialRetryMiddleware",
)


def test_item_pipelines_validate_normalize_publish_only():
    assert scrapy_settings.ITEM_PIPELINES == _EXPECTED_PIPELINES


def test_item_pipelines_sorted_by_priority():
    priorities = list(scrapy_settings.ITEM_PIPELINES.values())
    assert priorities == sorted(priorities)


def test_downloader_middlewares_include_stealth_rate_limit_retry():
    mw = scrapy_settings.DOWNLOADER_MIDDLEWARES
    joined = " ".join(mw)
    for fragment in _REQUIRED_MIDDLEWARE_SUBSTRINGS:
        assert fragment in joined


def test_asyncio_reactor_for_async_publish_and_optional_playwright_spiders():
    assert "AsyncioSelectorReactor" in scrapy_settings.TWISTED_REACTOR


def test_scrapy_list_exits_zero():
    """Smoke: project loads spiders with current settings."""
    repo = Path(__file__).resolve().parents[2]
    proc = run(
        [sys.executable, "-m", "scrapy", "list"],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
