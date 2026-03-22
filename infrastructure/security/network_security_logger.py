from __future__ import annotations

from config.settings import settings
from domain.observability import SyncCorrelationContext

from infrastructure.observability import message_codes as omc
from infrastructure.observability.event_logger import log_sync_event
from infrastructure.security.redaction import redact_url


def _corr(*, store_name: str | None = None) -> SyncCorrelationContext:
    return SyncCorrelationContext(
        run_id="network_security",
        spider_name="network_policy",
        store_name=(store_name or "*").strip() or "*",
    )


def _should_log() -> bool:
    return bool(getattr(settings, "ENABLE_STRUCTURED_SYNC_LOGS", False) or getattr(settings, "ENABLE_IN_MEMORY_TRACE_BUFFER", False))


def emit_outbound_host_validated(
    *,
    target_type: str,
    url: str,
    host: str,
    store_name: str | None = None,
) -> None:
    if not _should_log():
        return
    log_sync_event(
        "internal",
        "info",
        omc.OUTBOUND_HOST_VALIDATED,
        _corr(store_name=store_name),
        details={
            "target_type": target_type,
            "url": redact_url(url),
            "host": host,
        },
    )


def emit_outbound_host_blocked(
    *,
    target_type: str,
    url: str,
    host: str,
    reason: str | None,
    matched_rule: str | None,
    store_name: str | None = None,
) -> None:
    if not _should_log():
        return
    log_sync_event(
        "internal",
        "warning",
        omc.OUTBOUND_HOST_BLOCKED,
        _corr(store_name=store_name),
        details={
            "target_type": target_type,
            "url": redact_url(url),
            "host": host,
            "reason": reason,
            "matched_rule": matched_rule,
        },
    )


def emit_redirect_blocked(
    *,
    from_url: str,
    to_url: str,
    reason: str | None,
    redirect_hops: int,
    same_site: bool,
    store_name: str | None = None,
) -> None:
    if not _should_log():
        return
    log_sync_event(
        "internal",
        "warning",
        omc.REDIRECT_BLOCKED,
        _corr(store_name=store_name),
        details={
            "from_url": redact_url(from_url),
            "to_url": redact_url(to_url),
            "reason": reason,
            "redirect_hops": redirect_hops,
            "same_site": same_site,
        },
    )


def emit_redirect_allowed(
    *,
    from_url: str,
    to_url: str,
    same_site: bool,
    store_name: str | None = None,
) -> None:
    if not _should_log():
        return
    log_sync_event(
        "internal",
        "debug",
        omc.REDIRECT_ALLOWED,
        _corr(store_name=store_name),
        details={
            "from_url": redact_url(from_url),
            "to_url": redact_url(to_url),
            "same_site": same_site,
        },
    )


def emit_proxy_validated(*, proxy_host: str, store_name: str | None = None) -> None:
    if not _should_log():
        return
    log_sync_event(
        "internal",
        "info",
        omc.PROXY_VALIDATED,
        _corr(store_name=store_name),
        details={"proxy_host": proxy_host},
    )


def emit_proxy_blocked(*, reason: str, proxy_host: str, store_name: str | None = None) -> None:
    if not _should_log():
        return
    log_sync_event(
        "internal",
        "warning",
        omc.PROXY_BLOCKED,
        _corr(store_name=store_name),
        details={"reason": reason, "proxy_host": proxy_host},
    )


def emit_browser_nav_blocked(*, url: str, reason: str | None, store_name: str | None = None) -> None:
    if not _should_log():
        return
    log_sync_event(
        "internal",
        "warning",
        omc.BROWSER_NAV_BLOCKED,
        _corr(store_name=store_name),
        details={"url": redact_url(url), "reason": reason},
    )


def emit_ssrf_guard_blocked(*, url: str, reason: str | None, store_name: str | None = None) -> None:
    if not _should_log():
        return
    log_sync_event(
        "internal",
        "warning",
        omc.SSRF_GUARD_BLOCKED,
        _corr(store_name=store_name),
        details={"url": redact_url(url), "reason": reason},
    )


def emit_download_guard_blocked(*, url: str, reason: str, store_name: str | None = None) -> None:
    if not _should_log():
        return
    log_sync_event(
        "internal",
        "warning",
        omc.DOWNLOAD_GUARD_BLOCKED,
        _corr(store_name=store_name),
        details={"url": redact_url(url), "reason": reason},
    )
