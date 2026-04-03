from __future__ import annotations

from config.settings import settings as app_settings
from infrastructure.access.proxy_policy import should_install_rotating_proxy_middleware

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

# Active runtime: validate -> persist to scraper DB -> create outbox row.
# Legacy normalize/sync/publish pipelines are intentionally not wired into ITEM_PIPELINES.
# Default transport mode is plain HTTP; browser download handlers live in spider ``custom_settings`` only.
# Rotating proxies are opt-in via SCRAPY_ROTATING_PROXY_ENABLED + valid PROXY_LIST_PATH (2B).
ITEM_PIPELINES = {
    "infrastructure.pipelines.validate_pipeline.ValidatePipeline": 100,
    "infrastructure.pipelines.scraper_storage_pipeline.ScraperStoragePipeline": 200,
}

_USE_ROTATING = should_install_rotating_proxy_middleware(app_settings)
ROTATING_PROXY_LIST_PATH = (
    app_settings.PROXY_LIST_PATH.strip() if _USE_ROTATING and app_settings.PROXY_LIST_PATH else None
)

DOWNLOADER_MIDDLEWARES: dict[str, int] = {
    "infrastructure.middlewares.stealth_middleware.StealthMiddleware": 400,
    "infrastructure.middlewares.ratelimit_middleware.AccessAwareRateLimitMiddleware": 700,
    "infrastructure.middlewares.mobile_redirect_middleware.MobileRedirectMiddleware": 800,
    "infrastructure.middlewares.retry_middleware.ExponentialRetryMiddleware": 900,
}
if _USE_ROTATING:
    DOWNLOADER_MIDDLEWARES["rotating_proxies.middlewares.RotatingProxyMiddleware"] = 610
    DOWNLOADER_MIDDLEWARES["rotating_proxies.middlewares.BanDetectionMiddleware"] = 620

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
        "ROTATING_PROXY_LIST_PATH",
    )
    return {k: module_globals[k] for k in keys}


settings = get_scrapy_settings_dict()
