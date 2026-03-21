from __future__ import annotations

from config.settings import settings as app_settings

BOT_NAME = "uz_tech_scraper"
SPIDER_MODULES = ["infrastructure.spiders"]
NEWSPIDER_MODULE = "infrastructure.spiders"

CONCURRENT_REQUESTS = app_settings.SCRAPY_CONCURRENT_REQUESTS
DOWNLOAD_DELAY = app_settings.SCRAPY_DOWNLOAD_DELAY
LOG_LEVEL = app_settings.SCRAPY_LOG_LEVEL

AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1.0
AUTOTHROTTLE_MAX_DELAY = 30.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 2.0

ROBOTSTXT_OBEY = False
COOKIES_ENABLED = True

ITEM_PIPELINES = {
    "infrastructure.pipelines.validate_pipeline.ValidatePipeline": 100,
    "infrastructure.pipelines.normalize_pipeline.NormalizePipeline": 200,
    "infrastructure.pipelines.image_pipeline.ImagePipeline": 300,
    "infrastructure.pipelines.delta_pipeline.DeltaPipeline": 400,
}

DOWNLOADER_MIDDLEWARES = {
    "infrastructure.middlewares.stealth_middleware.StealthMiddleware": 400,
    "rotating_proxies.middlewares.RotatingProxyMiddleware": 610,
    "infrastructure.middlewares.ratelimit_middleware.AdaptiveRateLimitMiddleware": 700,
    "infrastructure.middlewares.mobile_redirect_middleware.MobileRedirectMiddleware": 800,
    "infrastructure.middlewares.retry_middleware.ExponentialRetryMiddleware": 900,
}

DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}

TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

PLAYWRIGHT_LAUNCH_OPTIONS = {
    "headless": True,
    "args": [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-infobars",
        "--window-position=0,0",
        "--ignore-certificate-errors",
        "--disable-extensions",
        "--disable-gpu",
    ],
}

PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 30000

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"

FEEDS: dict = {}


def get_scrapy_settings_dict() -> dict[str, object]:
    """Return all Scrapy-relevant settings as a plain dict (for tests / tooling)."""
    module_globals = globals()
    keys = (
        "BOT_NAME",
        "SPIDER_MODULES",
        "NEWSPIDER_MODULE",
        "CONCURRENT_REQUESTS",
        "DOWNLOAD_DELAY",
        "LOG_LEVEL",
        "AUTOTHROTTLE_ENABLED",
        "AUTOTHROTTLE_START_DELAY",
        "AUTOTHROTTLE_MAX_DELAY",
        "AUTOTHROTTLE_TARGET_CONCURRENCY",
        "ROBOTSTXT_OBEY",
        "COOKIES_ENABLED",
        "ITEM_PIPELINES",
        "DOWNLOADER_MIDDLEWARES",
        "DOWNLOAD_HANDLERS",
        "TWISTED_REACTOR",
        "PLAYWRIGHT_LAUNCH_OPTIONS",
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT",
        "REQUEST_FINGERPRINTER_IMPLEMENTATION",
        "FEEDS",
    )
    return {k: module_globals[k] for k in keys}


# Backwards-compatible alias if code expects a dict named `settings`
settings = get_scrapy_settings_dict()
