from __future__ import annotations

import threading
from dataclasses import dataclass
from urllib.parse import urlsplit

from application.release.rollout_policy_engine import is_feature_enabled
from config.settings import settings as app_settings
from infrastructure.access.store_profiles import get_store_profile


@dataclass(frozen=True)
class HeaderProfile:
    """Coherent desktop header profile used for rotation."""

    profile_id: str
    user_agent: str
    accept_language: str
    html_accept: str
    api_accept: str
    referer_policy: str = "passthrough"


_LEGACY_DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

_HEADER_PROFILES: dict[str, HeaderProfile] = {
    "chrome_win122_ru": HeaderProfile(
        profile_id="chrome_win122_ru",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        accept_language="ru-RU,ru;q=0.9,uz-UZ,uz;q=0.8,en;q=0.7",
        html_accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        api_accept="application/json, text/plain, */*",
        referer_policy="passthrough",
    ),
    "edge_win122_ru": HeaderProfile(
        profile_id="edge_win122_ru",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 "
            "Edg/122.0.0.0"
        ),
        accept_language="ru-RU,ru;q=0.9,en-US;q=0.8,uz-UZ;q=0.7",
        html_accept=(
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        ),
        api_accept="application/json, text/plain, */*",
        referer_policy="origin_on_navigation",
    ),
    "firefox_win124_ru": HeaderProfile(
        profile_id="firefox_win124_ru",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) "
            "Gecko/20100101 Firefox/124.0"
        ),
        accept_language="ru-RU,ru;q=0.9,uz-UZ;q=0.7,en-US;q=0.6",
        html_accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        api_accept="application/json, text/plain, */*",
        referer_policy="passthrough",
    ),
}

_DEFAULT_PROFILE_ORDER: tuple[str, ...] = (
    "chrome_win122_ru",
    "edge_win122_ru",
    "firefox_win124_ru",
)
_ROTATION_LOCK = threading.Lock()
_ROTATION_COUNTERS: dict[tuple[str, str, str], int] = {}


def _extract_host(url: str | None) -> str:
    if not url:
        return ""
    return (urlsplit(url).netloc or "").strip().lower()


def _extract_origin(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


def _infer_fetch_site(referer: str | None, request_url: str | None) -> str:
    if not referer:
        return "none"
    ref_host = _extract_host(referer)
    req_host = _extract_host(request_url)
    if ref_host and req_host and ref_host == req_host:
        return "same-origin"
    return "cross-site"


def _legacy_headers(
    purpose: str,
    *,
    referer: str | None = None,
) -> dict[str, str]:
    headers: dict[str, str] = {
        "User-Agent": _LEGACY_DESKTOP_UA,
        "Accept-Language": "ru-RU,ru;q=0.9,uz-UZ,uz;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    if purpose == "api":
        headers["Accept"] = "application/json, text/plain, */*"
    if referer:
        headers["Referer"] = referer
    elif purpose == "product":
        headers.setdefault("Sec-Fetch-Dest", "document")
        headers.setdefault("Sec-Fetch-Mode", "navigate")
    return headers


def _is_rotation_enabled(store_name: str) -> bool:
    if not app_settings.SCRAPY_HEADER_PROFILE_ROTATION_ENABLED:
        return False
    return is_feature_enabled("header_profile_rotation", store_name)


def _candidate_profile_ids(store_name: str) -> tuple[str, ...]:
    profile = get_store_profile(store_name)
    if profile.header_profile_ids:
        filtered = tuple(pid for pid in profile.header_profile_ids if pid in _HEADER_PROFILES)
        if filtered:
            return filtered
    return _DEFAULT_PROFILE_ORDER


def _select_profile(store_name: str, purpose: str, request_url: str | None) -> HeaderProfile:
    profile_ids = _candidate_profile_ids(store_name)
    domain = _extract_host(request_url) or "unknown-domain"
    key = (store_name, domain, (purpose or "listing").strip().lower() or "listing")
    with _ROTATION_LOCK:
        counter = _ROTATION_COUNTERS.get(key, 0)
        _ROTATION_COUNTERS[key] = counter + 1
    idx = counter % len(profile_ids)
    return _HEADER_PROFILES[profile_ids[idx]]


def _resolve_referer(
    profile: HeaderProfile,
    purpose: str,
    referer: str | None,
    request_url: str | None,
) -> str | None:
    if referer:
        return referer
    if profile.referer_policy == "origin_on_navigation" and purpose in {"listing", "product"}:
        return _extract_origin(request_url)
    return None


def _build_rotated_headers(
    store_name: str,
    purpose: str,
    *,
    referer: str | None = None,
    request_url: str | None = None,
) -> dict[str, str]:
    profile = _select_profile(store_name, purpose, request_url)
    headers: dict[str, str] = {
        "User-Agent": profile.user_agent,
        "Accept-Language": profile.accept_language,
        "Accept": profile.html_accept,
    }
    if purpose == "api":
        headers["Accept"] = profile.api_accept
        headers["Sec-Fetch-Dest"] = "empty"
        headers["Sec-Fetch-Mode"] = "cors"
    else:
        headers["Sec-Fetch-Dest"] = "document"
        headers["Sec-Fetch-Mode"] = "navigate"
        headers["Sec-Fetch-User"] = "?1"
    headers["Sec-Fetch-Site"] = _infer_fetch_site(referer=referer, request_url=request_url)
    final_referer = _resolve_referer(profile, purpose, referer, request_url)
    if final_referer:
        headers["Referer"] = final_referer
    return headers


def _reset_rotation_state_for_tests() -> None:
    """Test helper: reset profile rotation counters."""
    with _ROTATION_LOCK:
        _ROTATION_COUNTERS.clear()


def build_desktop_headers(
    store_name: str,
    purpose: str,
    *,
    referer: str | None = None,
    request_url: str | None = None,
) -> dict[str, str]:
    """Build desktop headers with optional User-Agent/header profile rotation."""
    normalized_store = (store_name or "").strip().lower() or "unknown"
    profile = get_store_profile(normalized_store)
    if profile.header_rotation_enabled is False:
        return _legacy_headers(purpose, referer=referer)
    if not _is_rotation_enabled(normalized_store):
        return _legacy_headers(purpose, referer=referer)
    return _build_rotated_headers(
        normalized_store,
        purpose,
        referer=referer,
        request_url=request_url,
    )
