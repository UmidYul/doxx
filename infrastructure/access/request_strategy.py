from __future__ import annotations

import json
import logging
from typing import Any, Literal

from application.release.rollout_policy_engine import is_feature_enabled
from config.settings import settings as app_settings
from infrastructure.access.access_metrics import access_metrics
from infrastructure.access.browser_policy import build_browser_request_meta
from infrastructure.access.proxy_policy import build_proxy_meta, is_proxy_available
from infrastructure.access.store_profiles import get_store_profile

logger = logging.getLogger(__name__)

Purpose = Literal["listing", "product", "api"]


def _log(event: str, **fields: Any) -> None:
    payload = {k: v for k, v in fields.items() if v is not None}
    logger.info("access_layer %s", json.dumps({"event": event, **payload}, default=str, ensure_ascii=False))


def should_use_proxy(
    store_name: str,
    purpose: str,
    prior_failures: int = 0,
    *,
    force_proxy: bool = False,
) -> bool:
    _ = purpose
    profile = get_store_profile(store_name)
    if profile.proxy_enabled is False:
        return False
    if force_proxy:
        return is_proxy_available() and (profile.fallback_to_proxy or profile.requires_proxy)
    if profile.requires_proxy:
        return is_proxy_available()
    if profile.mode == "http_with_proxy" and prior_failures >= app_settings.SCRAPY_PROXY_FALLBACK_FAILURE_THRESHOLD:
        return is_proxy_available()
    return False


def should_use_browser(
    store_name: str,
    purpose: str,
    prior_failures: int = 0,
    detected_signal: str | None = None,
    *,
    force_browser: bool = False,
    spider_supports_browser: bool = False,
) -> bool:
    _ = purpose
    profile = get_store_profile(store_name)
    if not is_feature_enabled("store_profile_runtime_control", store_name):
        return spider_supports_browser and profile.mode == "browser_required"
    if not is_feature_enabled("browser_escalation_policy", store_name):
        return spider_supports_browser and profile.mode == "browser_required"
    if profile.mode == "browser_required":
        return spider_supports_browser
    if force_browser and spider_supports_browser and profile.supports_browser:
        return True
    if profile.mode == "http_only":
        return False
    if not profile.supports_browser:
        return False
    if should_escalate_to_browser(
        store_name,
        purpose,
        detected_signal,
        prior_failures,
        spider_supports_browser=spider_supports_browser,
    ):
        return True
    return False


def should_escalate_to_browser(
    store_name: str,
    purpose: str,
    detected_signal: str | None,
    failure_count: int,
    *,
    spider_supports_browser: bool = False,
) -> bool:
    if not spider_supports_browser:
        return False
    if not is_feature_enabled("store_profile_runtime_control", store_name):
        return False
    if not is_feature_enabled("browser_escalation_policy", store_name):
        return False
    profile = get_store_profile(store_name)
    if profile.mode == "http_only":
        return False
    if not profile.supports_browser:
        return False
    if profile.mode == "browser_required":
        return False
    if not profile.fallback_to_browser:
        return False

    # Cloudflare interstitials: escalate on first observed challenge (failure_count is prior+1 from middleware).
    if detected_signal == "cloudflare_challenge" and failure_count >= 1:
        return True

    shellish = {"js_shell", "empty_shell", "cloudflare_challenge"}
    if detected_signal in shellish and failure_count >= app_settings.SCRAPY_ACCESS_SHELL_ESCALATE_AFTER:
        return True
    if (
        detected_signal in profile.ban_signals
        and failure_count >= app_settings.SCRAPY_BROWSER_FALLBACK_FAILURE_THRESHOLD
    ):
        return True
    _ = purpose
    return False


def should_escalate_to_proxy(
    store_name: str,
    purpose: str,
    detected_signal: str | None,
    failure_count: int,
) -> bool:
    _ = purpose
    if not is_proxy_available():
        return False
    profile = get_store_profile(store_name)
    if profile.proxy_enabled is False:
        return False
    if profile.mode == "http_only":
        return False
    if not profile.fallback_to_proxy and not profile.requires_proxy:
        return False
    if profile.requires_proxy:
        return False
    if detected_signal in ("access_denied", "transport_like_error_page", "empty_shell", "captcha"):
        if failure_count >= app_settings.SCRAPY_PROXY_FALLBACK_FAILURE_THRESHOLD:
            return True
    if profile.mode == "http_with_proxy" and failure_count >= 1:
        return True
    return False


def build_request_meta(
    store_name: str,
    purpose: Purpose | str,
    prior_failures: int = 0,
    force_browser: bool = False,
    force_proxy: bool = False,
    detected_signal: str | None = None,
    *,
    spider_supports_browser: bool = False,
    record_mode_metrics: bool = True,
    target_url: str | None = None,
) -> dict[str, Any]:
    """Deterministic meta for Scrapy Request (plain → optional proxy/browser).

    Store-aware resource governance (concurrency / browser / proxy budgets and
    backpressure) is applied **after** this returns, in
    ``BaseProductSpider.schedule_safe_request`` via
    ``infrastructure.access.resource_governance.apply_governance_to_request_meta``.
    Cost drivers (HTTP vs proxy vs browser, retries) are recorded at schedule time
    via ``perf_collector.record_scheduled_request_cost`` (8C).
    """
    profile = get_store_profile(store_name)
    meta: dict[str, Any] = {
        "store_name": store_name,
        "access_purpose": purpose,
        "prior_failures": prior_failures,
    }

    use_browser = should_use_browser(
        store_name,
        str(purpose),
        prior_failures,
        detected_signal,
        force_browser=force_browser,
        spider_supports_browser=spider_supports_browser,
    )
    use_proxy = should_use_proxy(store_name, str(purpose), prior_failures, force_proxy=force_proxy)

    mode_selected = "plain"

    def _bump_mode(metric_key: str) -> None:
        if record_mode_metrics:
            access_metrics.bump(metric_key)

    if profile.mode == "browser_required":
        if spider_supports_browser:
            meta.update(build_browser_request_meta(store_name, str(purpose)))
            mode_selected = "browser"
            _bump_mode("requests_browser_total")
        else:
            logger.warning(
                "Store %s is browser_required but spider has no Playwright download handler — falling back to plain HTTP",
                store_name,
            )
            _bump_mode("requests_plain_http_total")
            mode_selected = "plain"
    elif use_browser and spider_supports_browser:
        meta.update(build_browser_request_meta(store_name, str(purpose)))
        mode_selected = "browser"
        _bump_mode("requests_browser_total")
    elif use_proxy or (profile.requires_proxy and profile.proxy_enabled is not False and is_proxy_available()):
        extra = build_proxy_meta(store_name, str(purpose), target_url=target_url)
        pu = extra.get("proxy")
        if pu and target_url:
            from infrastructure.security.proxy_security import should_allow_proxy_for_target

            if not should_allow_proxy_for_target(str(pu), target_url, app_settings):
                extra = {}
        if extra:
            meta.update(extra)
            mode_selected = "proxy"
            _bump_mode("requests_proxy_total")
        else:
            _bump_mode("requests_plain_http_total")
            mode_selected = "plain"
    else:
        _bump_mode("requests_plain_http_total")
        mode_selected = "plain"

    meta["access_mode_selected"] = mode_selected
    _log(
        "REQUEST_MODE_SELECTED",
        store=store_name,
        purpose=purpose,
        mode=mode_selected,
        retry_count=prior_failures,
        reason=detected_signal,
    )
    return meta

