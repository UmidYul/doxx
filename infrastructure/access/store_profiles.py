from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AccessMode = Literal["http_only", "http_with_proxy", "browser_required", "browser_fallback"]
ProxyMode = Literal["rotating", "sticky"]

_COMMON_BAN_SIGNALS: list[str] = [
    "captcha",
    "cloudflare_challenge",
    "access_denied",
    "js_shell",
    "empty_shell",
    "transport_like_error_page",
]


class StoreAccessProfile(BaseModel):
    """Per-store fetch policy: cheapest path first, optional escalation."""

    model_config = {"frozen": True}

    store_name: str
    mode: AccessMode
    requires_proxy: bool = False
    supports_browser: bool = True
    browser_only_paths: list[str] = Field(default_factory=list)
    max_concurrent_requests: int | None = None
    download_delay: float | None = None
    retry_http_codes: list[int] = Field(default_factory=lambda: [429, 503, 520, 521, 522])
    ban_signals: list[str] = Field(default_factory=lambda: list(_COMMON_BAN_SIGNALS))
    empty_body_threshold: int = 256
    fallback_to_browser: bool = True
    fallback_to_proxy: bool = True
    jitter_enabled: bool | None = None
    jitter_min_seconds: float | None = None
    jitter_max_seconds: float | None = None
    header_rotation_enabled: bool | None = None
    header_profile_ids: list[str] | None = None
    proxy_enabled: bool | None = None
    proxy_pool_path: str | None = None
    proxy_mode: ProxyMode | None = None
    proxy_sticky_requests: int | None = None
    proxy_cooldown_seconds: int | None = None
    proxy_ban_score_threshold: int | None = None
    proxy_max_consecutive_failures: int | None = None
    honeypot_filter_enabled: bool | None = None
    honeypot_tokens: list[str] | None = None


_DEFAULT = StoreAccessProfile(
    store_name="_default",
    mode="browser_fallback",
    requires_proxy=False,
    supports_browser=True,
    browser_only_paths=[],
    max_concurrent_requests=None,
    download_delay=None,
    retry_http_codes=[429, 503, 520, 521, 522],
    ban_signals=list(_COMMON_BAN_SIGNALS),
    empty_body_threshold=256,
    fallback_to_browser=True,
    fallback_to_proxy=True,
)

_PROFILES: dict[str, StoreAccessProfile] = {
    "mediapark": StoreAccessProfile(
        store_name="mediapark",
        mode="browser_fallback",
        requires_proxy=False,
        supports_browser=True,
        browser_only_paths=[],
        max_concurrent_requests=None,
        download_delay=1.0,
        retry_http_codes=[429, 503, 520, 521, 522],
        ban_signals=list(_COMMON_BAN_SIGNALS),
        empty_body_threshold=400,
        fallback_to_browser=True,
        fallback_to_proxy=True,
    ),
    "uzum": StoreAccessProfile(
        store_name="uzum",
        mode="browser_fallback",
        requires_proxy=False,
        supports_browser=True,
        browser_only_paths=[],
        max_concurrent_requests=10,
        download_delay=1.0,
        retry_http_codes=[429, 503, 520, 521, 522],
        ban_signals=list(_COMMON_BAN_SIGNALS),
        empty_body_threshold=256,
        fallback_to_browser=True,
        fallback_to_proxy=False,
    ),
    "texnomart": StoreAccessProfile(
        store_name="texnomart",
        mode="browser_fallback",
        requires_proxy=False,
        supports_browser=True,
        browser_only_paths=[],
        max_concurrent_requests=10,
        download_delay=1.0,
        retry_http_codes=[429, 503, 520, 521, 522],
        ban_signals=list(_COMMON_BAN_SIGNALS),
        empty_body_threshold=320,
        fallback_to_browser=True,
        fallback_to_proxy=True,
    ),
    "alifshop": StoreAccessProfile(
        store_name="alifshop",
        mode="http_only",
        requires_proxy=False,
        supports_browser=False,
        browser_only_paths=[],
        max_concurrent_requests=6,
        download_delay=1.0,
        retry_http_codes=[429, 503, 520, 521, 522],
        ban_signals=list(_COMMON_BAN_SIGNALS),
        empty_body_threshold=320,
        fallback_to_browser=False,
        fallback_to_proxy=True,
    ),
}


def get_store_profile(store_name: str) -> StoreAccessProfile:
    key = (store_name or "").strip().lower()
    if key in _PROFILES:
        return _PROFILES[key]
    return _DEFAULT.model_copy(update={"store_name": store_name or key or "unknown"})
