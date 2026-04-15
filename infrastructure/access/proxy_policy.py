from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from application.release.rollout_policy_engine import is_feature_enabled
from config.settings import Settings, settings as app_settings
from infrastructure.access.store_profiles import ProxyMode, StoreAccessProfile, get_store_profile

logger = logging.getLogger(__name__)


@dataclass
class ProxyHealthState:
    """Runtime proxy health used by policy hardening."""

    health_score: float = 100.0
    ban_score: int = 0
    consecutive_failures: int = 0
    cooldown_until_monotonic: float = 0.0
    last_reason: str | None = None


@dataclass
class _StickyLease:
    proxy_url: str
    uses_left: int


@dataclass(frozen=True)
class _PoolCacheEntry:
    mtime: float
    urls: tuple[str, ...]


_POOL_CACHE_LOCK = threading.Lock()
_POOL_CACHE: dict[str, _PoolCacheEntry] = {}

_SELECTOR_LOCK = threading.Lock()
_ROTATION_COUNTERS: dict[tuple[str, str, str], int] = {}
_STICKY_LEASES: dict[tuple[str, str], _StickyLease] = {}

_HEALTH_LOCK = threading.Lock()
_PROXY_HEALTH: dict[str, ProxyHealthState] = {}

_BAN_LIKE_REASONS: frozenset[str] = frozenset(
    {
        "captcha",
        "access_denied",
        "transport_like_error_page",
        "cloudflare_challenge",
        "proxy_rejected",
        "http_403",
        "http_429",
    }
)


def is_proxy_available(settings: Settings | None = None) -> bool:
    """True when the global proxy list path is configured and readable."""
    s = settings or app_settings
    path = (s.PROXY_LIST_PATH or "").strip()
    return _pool_path_available(path)


def _pool_path_available(path: str) -> bool:
    if not path:
        return False
    if not os.path.isfile(path):
        logger.warning("PROXY_LIST_PATH set but file missing (%s) - proxy disabled for this run", path)
        return False
    return True


def _normalize_proxy_url(url: str) -> str | None:
    clean = (url or "").strip()
    if not clean or clean.startswith("#"):
        return None
    if not clean.startswith("http://") and not clean.startswith("https://"):
        clean = f"http://{clean}"
    return clean


def _read_proxy_urls(path: str) -> tuple[str, ...]:
    if not _pool_path_available(path):
        return ()
    try:
        mtime = os.path.getmtime(path)
    except OSError as exc:
        logger.warning("Could not stat proxy list %s: %s", path, exc)
        return ()

    with _POOL_CACHE_LOCK:
        cached = _POOL_CACHE.get(path)
        if cached and cached.mtime == mtime:
            return cached.urls

    urls: list[str] = []
    seen: set[str] = set()
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                normalized = _normalize_proxy_url(line)
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                urls.append(normalized)
    except OSError as exc:
        logger.warning("Could not read proxy list %s: %s", path, exc)
        return ()

    cached_entry = _PoolCacheEntry(mtime=mtime, urls=tuple(urls))
    with _POOL_CACHE_LOCK:
        _POOL_CACHE[path] = cached_entry
    return cached_entry.urls


def should_install_rotating_proxy_middleware(settings: Settings | None = None) -> bool:
    """Register ``RotatingProxyMiddleware`` only when explicitly enabled and list is readable."""
    s = settings or app_settings
    if not getattr(s, "SCRAPY_ROTATING_PROXY_ENABLED", False):
        return False
    return is_proxy_available(s)


def should_enable_rotating_proxies(store_name: str, settings: Settings | None = None) -> bool:
    """Whether this store should use the globally installed rotating proxy middleware."""
    s = settings or app_settings
    if not getattr(s, "SCRAPY_ROTATING_PROXY_ENABLED", False):
        return False
    if not is_proxy_available(s):
        return False
    profile = get_store_profile(store_name)
    if profile.proxy_enabled is False:
        return False
    return profile.requires_proxy or profile.mode == "http_with_proxy"


def _hardening_enabled(store_name: str, settings: Settings) -> bool:
    if not getattr(settings, "SCRAPY_PROXY_POLICY_HARDENING_ENABLED", False):
        return False
    return is_feature_enabled("proxy_policy_hardening", store_name)


def _resolve_pool_path(store_name: str, profile: StoreAccessProfile, settings: Settings) -> str:
    if _hardening_enabled(store_name, settings):
        per_store = (profile.proxy_pool_path or "").strip()
        if per_store:
            return per_store
    return (settings.PROXY_LIST_PATH or "").strip()


def _resolve_mode(profile: StoreAccessProfile, settings: Settings) -> ProxyMode:
    if profile.proxy_mode in ("sticky", "rotating"):
        return profile.proxy_mode
    raw = str(getattr(settings, "SCRAPY_PROXY_POLICY_DEFAULT_MODE", "rotating") or "rotating").strip().lower()
    if raw == "sticky":
        return "sticky"
    return "rotating"


def _resolve_sticky_requests(profile: StoreAccessProfile, settings: Settings) -> int:
    if profile.proxy_sticky_requests is not None:
        return max(1, int(profile.proxy_sticky_requests))
    return int(getattr(settings, "SCRAPY_PROXY_STICKY_REQUESTS_DEFAULT", 20))


def _resolve_cooldown_seconds(profile: StoreAccessProfile, settings: Settings) -> int:
    if profile.proxy_cooldown_seconds is not None:
        return max(1, int(profile.proxy_cooldown_seconds))
    return int(getattr(settings, "SCRAPY_PROXY_COOLDOWN_SECONDS_DEFAULT", 300))


def _resolve_ban_score_threshold(profile: StoreAccessProfile, settings: Settings) -> int:
    if profile.proxy_ban_score_threshold is not None:
        return max(1, int(profile.proxy_ban_score_threshold))
    return int(getattr(settings, "SCRAPY_PROXY_BAN_SCORE_THRESHOLD", 3))


def _resolve_max_consecutive_failures(profile: StoreAccessProfile, settings: Settings) -> int:
    if profile.proxy_max_consecutive_failures is not None:
        return max(1, int(profile.proxy_max_consecutive_failures))
    return int(getattr(settings, "SCRAPY_PROXY_MAX_CONSECUTIVE_FAILURES", 2))


def _extract_domain(url: str | None) -> str:
    if not url:
        return "unknown-domain"
    return (urlsplit(url).netloc or "").strip().lower() or "unknown-domain"


def _is_in_cooldown(proxy_url: str, now: float) -> bool:
    with _HEALTH_LOCK:
        state = _PROXY_HEALTH.get(proxy_url)
        if state is None:
            return False
        return state.cooldown_until_monotonic > now


def _health_rank(proxy_url: str) -> tuple[int, float, int]:
    with _HEALTH_LOCK:
        state = _PROXY_HEALTH.get(proxy_url)
        if state is None:
            return (0, -100.0, 0)
        return (state.ban_score, -state.health_score, state.consecutive_failures)


def _select_rotating_proxy(
    candidates: list[str],
    *,
    store_name: str,
    purpose: str,
    pool_key: str,
) -> str:
    ranked = sorted(candidates, key=_health_rank)
    rotation_key = (store_name, purpose, pool_key)
    with _SELECTOR_LOCK:
        counter = _ROTATION_COUNTERS.get(rotation_key, 0)
        _ROTATION_COUNTERS[rotation_key] = counter + 1
    return ranked[counter % len(ranked)]


def _select_sticky_proxy(
    candidates: list[str],
    *,
    store_name: str,
    purpose: str,
    pool_key: str,
    domain: str,
    sticky_requests: int,
) -> str:
    sticky_key = (store_name, domain)
    with _SELECTOR_LOCK:
        existing = _STICKY_LEASES.get(sticky_key)
        if existing and existing.proxy_url in candidates and existing.uses_left > 0:
            existing.uses_left -= 1
            _STICKY_LEASES[sticky_key] = existing
            return existing.proxy_url

    selected = _select_rotating_proxy(
        candidates,
        store_name=store_name,
        purpose=f"{purpose}:sticky",
        pool_key=pool_key,
    )
    uses_left = max(0, sticky_requests - 1)
    with _SELECTOR_LOCK:
        _STICKY_LEASES[sticky_key] = _StickyLease(proxy_url=selected, uses_left=uses_left)
    return selected


def _select_proxy_by_policy(
    *,
    store_name: str,
    purpose: str,
    target_url: str | None,
    pool_path: str,
    profile: StoreAccessProfile,
    settings: Settings,
    proxy_urls: tuple[str, ...],
) -> str | None:
    now = time.monotonic()
    selectable = [url for url in proxy_urls if not _is_in_cooldown(url, now)]
    if not selectable:
        logger.warning("Proxy pool exhausted by cooldown (store=%s, purpose=%s)", store_name, purpose)
        return None

    mode = _resolve_mode(profile, settings)
    if mode == "sticky":
        return _select_sticky_proxy(
            selectable,
            store_name=store_name,
            purpose=purpose,
            pool_key=pool_path,
            domain=_extract_domain(target_url),
            sticky_requests=_resolve_sticky_requests(profile, settings),
        )
    return _select_rotating_proxy(
        selectable,
        store_name=store_name,
        purpose=purpose,
        pool_key=pool_path,
    )


def build_proxy_meta(
    store_name: str,
    purpose: str,
    settings: Settings | None = None,
    *,
    target_url: str | None = None,
) -> dict[str, Any]:
    """Per-request proxy meta; empty dict when proxy is unavailable or not selected."""
    s = settings or app_settings
    profile = get_store_profile(store_name)
    if profile.proxy_enabled is False:
        return {}
    if not profile.fallback_to_proxy and not profile.requires_proxy:
        return {}

    pool_path = _resolve_pool_path(store_name, profile, s)
    if not _pool_path_available(pool_path):
        return {}
    proxy_urls = _read_proxy_urls(pool_path)
    if not proxy_urls:
        logger.warning("Proxy list empty or unreadable - skipping proxy meta")
        return {}

    hardened = _hardening_enabled(store_name, s)
    selected = (
        _select_proxy_by_policy(
            store_name=store_name,
            purpose=purpose,
            target_url=target_url,
            pool_path=pool_path,
            profile=profile,
            settings=s,
            proxy_urls=proxy_urls,
        )
        if hardened
        else proxy_urls[0]
    )
    if not selected:
        return {}

    from infrastructure.security import network_security_logger as net_log
    from infrastructure.security.proxy_security import validate_proxy_url

    decision = validate_proxy_url(selected, s)
    if not decision.allowed:
        proxy_host = ""
        if decision.proxy_url_masked:
            try:
                proxy_host = (urlsplit(decision.proxy_url_masked).hostname or "").strip()
            except Exception:
                proxy_host = ""
        net_log.emit_proxy_blocked(
            reason=decision.reason or "proxy_rejected",
            proxy_host=proxy_host or "[redacted]",
            store_name=store_name,
        )
        logger.warning("Proxy URL rejected by network policy (%s) - skipping proxy meta", decision.reason)
        mark_proxy_result(
            selected,
            success=False,
            reason=decision.reason or "proxy_rejected",
            settings=s,
            store_name=store_name,
        )
        return {}

    mode_value: str = _resolve_mode(profile, s) if hardened else "legacy"
    return {
        "proxy": selected,
        "access_used_manual_proxy": True,
        "access_proxy_mode": mode_value,
    }


def mark_proxy_result(
    proxy_url: str,
    *,
    success: bool,
    reason: str | None = None,
    settings: Settings | None = None,
    store_name: str | None = None,
) -> None:
    """Update proxy health state from response outcome signals."""
    normalized = _normalize_proxy_url(proxy_url)
    if not normalized:
        return
    s = settings or app_settings
    if not getattr(s, "SCRAPY_PROXY_POLICY_HARDENING_ENABLED", False):
        return
    if store_name and not is_feature_enabled("proxy_policy_hardening", store_name):
        return

    profile = get_store_profile(store_name or "")
    ban_threshold = _resolve_ban_score_threshold(profile, s)
    max_failures = _resolve_max_consecutive_failures(profile, s)
    cooldown_seconds = _resolve_cooldown_seconds(profile, s)

    now = time.monotonic()
    with _HEALTH_LOCK:
        state = _PROXY_HEALTH.setdefault(normalized, ProxyHealthState())
        if success:
            state.consecutive_failures = 0
            state.ban_score = max(0, state.ban_score - 1)
            state.health_score = min(100.0, state.health_score + 3.0)
            state.last_reason = reason or "success"
            if state.cooldown_until_monotonic <= now:
                state.cooldown_until_monotonic = 0.0
            return

        ban_like = str(reason or "").strip().lower() in _BAN_LIKE_REASONS
        state.consecutive_failures += 1
        state.ban_score += 2 if ban_like else 1
        state.health_score = max(0.0, state.health_score - (20.0 if ban_like else 10.0))
        state.last_reason = reason or "failure"
        if state.ban_score >= ban_threshold or state.consecutive_failures >= max_failures:
            state.cooldown_until_monotonic = max(
                state.cooldown_until_monotonic,
                now + float(cooldown_seconds),
            )


def get_proxy_health_snapshot() -> dict[str, dict[str, Any]]:
    """Debug-friendly snapshot of in-memory proxy health state."""
    now = time.monotonic()
    with _HEALTH_LOCK:
        snapshot: dict[str, dict[str, Any]] = {}
        for proxy_url, state in _PROXY_HEALTH.items():
            snapshot[proxy_url] = {
                "health_score": round(state.health_score, 2),
                "ban_score": int(state.ban_score),
                "consecutive_failures": int(state.consecutive_failures),
                "cooldown_remaining_seconds": max(0.0, round(state.cooldown_until_monotonic - now, 2)),
                "last_reason": state.last_reason,
            }
        return snapshot


def _reset_proxy_policy_state_for_tests() -> None:
    """Reset in-memory proxy policy state for deterministic unit tests."""
    with _POOL_CACHE_LOCK:
        _POOL_CACHE.clear()
    with _SELECTOR_LOCK:
        _ROTATION_COUNTERS.clear()
        _STICKY_LEASES.clear()
    with _HEALTH_LOCK:
        _PROXY_HEALTH.clear()
