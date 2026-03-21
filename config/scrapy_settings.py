from __future__ import annotations

from config.settings import settings as app_settings

BOT_NAME = "moscraper"
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

# Default: plain HTTP (no browser download handlers here). Spiders that need JS
# (e.g. ``UzumSpider``) register the scrapy-playwright handler only in their own
# ``custom_settings`` and use ``Request(meta={"playwright": True})``.
# No image-download pipeline: spiders emit URLs only; CRM downloads and processes media.
# No delta/cache pipeline: no local diff or upsert; publish after normalize (RabbitMQ).
# Pipeline order: validate → normalize → publish (RabbitMQ).
ITEM_PIPELINES = {
    "infrastructure.pipelines.validate_pipeline.ValidatePipeline": 100,
    "infrastructure.pipelines.normalize_pipeline.NormalizePipeline": 200,
    "infrastructure.pipelines.publish_pipeline.PublishPipeline": 300,
}

DOWNLOADER_MIDDLEWARES = {
    "infrastructure.middlewares.stealth_middleware.StealthMiddleware": 400,
    "rotating_proxies.middlewares.RotatingProxyMiddleware": 610,
    "infrastructure.middlewares.ratelimit_middleware.AdaptiveRateLimitMiddleware": 700,
    "infrastructure.middlewares.mobile_redirect_middleware.MobileRedirectMiddleware": 800,
    "infrastructure.middlewares.retry_middleware.ExponentialRetryMiddleware": 900,
}

TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"

FEEDS: dict = {}


def get_scrapy_settings_dict() -> dict[str, object]:
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
        "TWISTED_REACTOR",
        "REQUEST_FINGERPRINTER_IMPLEMENTATION",
        "FEEDS",
    )
    return {k: module_globals[k] for k in keys}


settings = get_scrapy_settings_dict()
