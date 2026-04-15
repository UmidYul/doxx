from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from email.utils import parsedate_to_datetime
from typing import Mapping
import time

from config.settings import Settings, settings as app_settings

_LIMIT_HEADERS: tuple[str, ...] = (
    "X-RateLimit-Limit",
    "RateLimit-Limit",
)
_REMAINING_HEADERS: tuple[str, ...] = (
    "X-RateLimit-Remaining",
    "RateLimit-Remaining",
)
_RESET_HEADERS: tuple[str, ...] = (
    "X-RateLimit-Reset",
    "RateLimit-Reset",
)
_RETRY_AFTER_HEADERS: tuple[str, ...] = ("Retry-After",)


def _decode_header(
    headers: Mapping[bytes, bytes] | object,
    candidates: tuple[str, ...],
) -> str | None:
    getter = getattr(headers, "get", None)
    if not callable(getter):
        return None
    for name in candidates:
        raw = getter(name.encode("latin-1"))
        if raw is None:
            raw = getter(name)
        if raw is None:
            continue
        if isinstance(raw, (list, tuple)):
            raw = raw[0] if raw else None
        if raw is None:
            continue
        if isinstance(raw, bytes):
            text = raw.decode("latin-1", errors="ignore").strip()
        else:
            text = str(raw).strip()
        if text:
            return text
    return None


def _parse_int(raw: str | None) -> int | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _parse_retry_after_seconds(raw: str | None, *, now_epoch: float) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        seconds = float(text)
        return max(0.0, seconds)
    except (TypeError, ValueError):
        pass
    try:
        dt = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return max(0.0, dt.timestamp() - now_epoch)


def _parse_reset_wait_seconds(raw: str | None, *, now_epoch: float) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    if value <= 0.0:
        return None
    # Common patterns: absolute unix epoch or relative seconds.
    if value > now_epoch + 1.0:
        return max(0.0, value - now_epoch)
    return value


@dataclass(frozen=True)
class RateLimitHeaderSnapshot:
    """Parsed rate-limit hints extracted from HTTP headers."""

    limit: int | None = None
    remaining: int | None = None
    reset_wait_seconds: float | None = None
    retry_after_seconds: float | None = None

    @property
    def has_hints(self) -> bool:
        return any(
            value is not None
            for value in (
                self.limit,
                self.remaining,
                self.reset_wait_seconds,
                self.retry_after_seconds,
            )
        )


@dataclass(frozen=True)
class BackoffDecision:
    """Policy decision for explicit backoff analysis."""

    status: int
    reason: str
    retry_allowed: bool
    wait_seconds: float
    cooldown_seconds: float
    actions: tuple[str, ...]


class ExplicitBackoffEngine:
    """Classify response status + rate-limit headers into explicit backoff decisions."""

    _SUPPORTED_STATUSES: frozenset[int] = frozenset({403, 408, 429, 500, 502, 503, 504})

    def __init__(
        self,
        *,
        base_seconds: float = 1.0,
        max_seconds: float = 90.0,
        cooldown_max_seconds: float = 300.0,
        respect_retry_after: bool = True,
        strict_429: bool = True,
    ) -> None:
        self._base_seconds = max(0.0, float(base_seconds))
        self._max_seconds = max(self._base_seconds, float(max_seconds))
        self._cooldown_max_seconds = max(0.0, float(cooldown_max_seconds))
        self._respect_retry_after = bool(respect_retry_after)
        self._strict_429 = bool(strict_429)

    @classmethod
    def from_settings(cls, s: Settings | None = None) -> ExplicitBackoffEngine:
        cfg = s or app_settings
        return cls(
            base_seconds=float(getattr(cfg, "SCRAPY_BACKOFF_BASE_SECONDS", 1.0)),
            max_seconds=float(getattr(cfg, "SCRAPY_BACKOFF_MAX_SECONDS", 90.0)),
            cooldown_max_seconds=float(getattr(cfg, "SCRAPY_BACKOFF_COOLDOWN_MAX_SECONDS", 300.0)),
            respect_retry_after=bool(getattr(cfg, "SCRAPY_BACKOFF_RESPECT_RETRY_AFTER", True)),
            strict_429=bool(getattr(cfg, "SCRAPY_BACKOFF_429_STRICT", True)),
        )

    def supports_status(self, status: int) -> bool:
        return int(status) in self._SUPPORTED_STATUSES

    def parse_headers(
        self,
        headers: Mapping[bytes, bytes] | object,
        *,
        now_epoch: float | None = None,
    ) -> RateLimitHeaderSnapshot:
        now = float(now_epoch if now_epoch is not None else time.time())
        limit = _parse_int(_decode_header(headers, _LIMIT_HEADERS))
        remaining = _parse_int(_decode_header(headers, _REMAINING_HEADERS))
        retry_after_seconds = _parse_retry_after_seconds(
            _decode_header(headers, _RETRY_AFTER_HEADERS),
            now_epoch=now,
        )
        reset_wait_seconds = _parse_reset_wait_seconds(
            _decode_header(headers, _RESET_HEADERS),
            now_epoch=now,
        )
        return RateLimitHeaderSnapshot(
            limit=limit,
            remaining=remaining,
            reset_wait_seconds=reset_wait_seconds,
            retry_after_seconds=retry_after_seconds,
        )

    def classify(
        self,
        *,
        status: int,
        prior_failures: int,
        headers_snapshot: RateLimitHeaderSnapshot | None = None,
    ) -> BackoffDecision:
        http_status = int(status)
        snapshot = headers_snapshot or RateLimitHeaderSnapshot()
        if not self.supports_status(http_status):
            return BackoffDecision(
                status=http_status,
                reason="policy_not_applicable",
                retry_allowed=False,
                wait_seconds=0.0,
                cooldown_seconds=0.0,
                actions=(),
            )

        wait = self._exp_wait(prior_failures)
        if http_status == 403:
            return BackoffDecision(
                status=http_status,
                reason="http_403_forbidden",
                retry_allowed=False,
                wait_seconds=0.0,
                cooldown_seconds=min(self._cooldown_max_seconds, max(wait, 5.0)),
                actions=("rotate_proxy", "rotate_session"),
            )
        if http_status == 408:
            return BackoffDecision(
                status=http_status,
                reason="http_408_timeout",
                retry_allowed=True,
                wait_seconds=wait,
                cooldown_seconds=0.0,
                actions=(),
            )
        if http_status == 429:
            return self._classify_429(wait, snapshot)
        if http_status == 500:
            return BackoffDecision(
                status=http_status,
                reason="http_500_server_error",
                retry_allowed=True,
                wait_seconds=wait,
                cooldown_seconds=0.0,
                actions=(),
            )
        if http_status == 502:
            return BackoffDecision(
                status=http_status,
                reason="http_502_bad_gateway",
                retry_allowed=True,
                wait_seconds=wait,
                cooldown_seconds=0.0,
                actions=(),
            )
        if http_status == 503:
            return BackoffDecision(
                status=http_status,
                reason="http_503_upstream_error",
                retry_allowed=True,
                wait_seconds=wait,
                cooldown_seconds=min(self._cooldown_max_seconds, wait),
                actions=("domain_cooldown",),
            )
        return BackoffDecision(
            status=http_status,
            reason="http_504_gateway_timeout",
            retry_allowed=True,
            wait_seconds=wait,
            cooldown_seconds=0.0,
            actions=(),
        )

    def _classify_429(
        self,
        exp_wait: float,
        snapshot: RateLimitHeaderSnapshot,
    ) -> BackoffDecision:
        wait_candidates = [exp_wait]
        reason = "http_429_exponential"
        if self._respect_retry_after and snapshot.retry_after_seconds is not None:
            wait_candidates.append(snapshot.retry_after_seconds)
            reason = "http_429_retry_after"
        if snapshot.remaining == 0 and snapshot.reset_wait_seconds is not None:
            wait_candidates.append(snapshot.reset_wait_seconds)
            if reason != "http_429_retry_after":
                reason = "http_429_ratelimit_reset"

        wait = max(wait_candidates)
        if self._strict_429 and wait <= 0.0:
            wait = exp_wait
        cooldown = min(self._cooldown_max_seconds, wait)
        return BackoffDecision(
            status=429,
            reason=reason,
            retry_allowed=True,
            wait_seconds=wait,
            cooldown_seconds=cooldown,
            actions=("domain_cooldown",),
        )

    def _exp_wait(self, prior_failures: int) -> float:
        retries = max(0, int(prior_failures))
        wait = self._base_seconds * (2**retries)
        return min(self._max_seconds, max(0.0, wait))
