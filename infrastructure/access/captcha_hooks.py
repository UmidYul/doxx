from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlsplit

import scrapy.http

from config.settings import Settings, settings as app_settings
from infrastructure.access.ban_detector import detect_ban_signal

logger = logging.getLogger(__name__)

_REDIRECT_STATUSES: frozenset[int] = frozenset({301, 302, 303, 307, 308})
_CHALLENGE_MARKERS: tuple[bytes, ...] = (
    b"captcha",
    b"g-recaptcha",
    b"hcaptcha",
    b"cf-chl",
    b"challenge-form",
    b"verify you are human",
    b"turnstile",
)
_REDIRECT_CHALLENGE_HINTS: tuple[str, ...] = (
    "captcha",
    "challenge",
    "verify",
    "blocked",
    "sorry",
)


@dataclass(frozen=True)
class CaptchaDetectionResult:
    """Captcha/challenge detection output consumed by middleware hooks."""

    signal: str | None
    markers: tuple[str, ...] = ()
    suspicious_redirect: bool = False
    redirect_target: str | None = None

    def is_captcha_related(self) -> bool:
        if self.signal in {"captcha", "cloudflare_challenge"}:
            return True
        if self.suspicious_redirect:
            return True
        return bool(self.markers)


@dataclass(frozen=True)
class CaptchaSolveResult:
    """Captcha solver hook result."""

    handled: bool
    solver: str
    reason: str
    retry_request: scrapy.http.Request | None = None
    token: str | None = None
    extra_meta: dict[str, str] = field(default_factory=dict)


class CaptchaSolver(Protocol):
    """Interface for pluggable captcha solvers."""

    def solve(
        self,
        request: scrapy.http.Request,
        response: scrapy.http.Response,
        spider,
        *,
        detection: CaptchaDetectionResult,
        store: str,
        purpose: str,
    ) -> CaptchaSolveResult:
        """Attempt captcha resolution and optionally return a retry request."""


class NoopCaptchaSolver:
    """No-op solver used when no external solver backend is configured."""

    def __init__(self, *, reason: str = "solver_not_configured") -> None:
        self._reason = reason

    def solve(
        self,
        request: scrapy.http.Request,
        response: scrapy.http.Response,
        spider,
        *,
        detection: CaptchaDetectionResult,
        store: str,
        purpose: str,
    ) -> CaptchaSolveResult:
        _ = request, response, spider, detection, store, purpose
        return CaptchaSolveResult(
            handled=False,
            solver="noop",
            reason=self._reason,
            retry_request=None,
            token=None,
            extra_meta={},
        )


class CaptchaSignalDetector:
    """Detect captcha-like pages and suspicious challenge redirects."""

    def __init__(self, *, suspicious_redirect_enabled: bool = True) -> None:
        self._suspicious_redirect_enabled = suspicious_redirect_enabled

    @staticmethod
    def _body_lower(response: scrapy.http.Response) -> bytes:
        return (response.body or b"").lower()

    @staticmethod
    def _decode_location(response: scrapy.http.Response) -> str | None:
        raw = response.headers.get(b"Location")
        if not raw:
            return None
        if isinstance(raw, bytes):
            return raw.decode("latin-1", errors="ignore").strip() or None
        return str(raw).strip() or None

    @staticmethod
    def _host(url: str) -> str:
        return (urlsplit(url).netloc or "").strip().lower()

    def _suspicious_redirect(
        self,
        request: scrapy.http.Request | None,
        response: scrapy.http.Response,
    ) -> tuple[bool, str | None]:
        if not self._suspicious_redirect_enabled:
            return False, None
        location = self._decode_location(response)
        target = location or response.url
        if response.status not in _REDIRECT_STATUSES and not location:
            return False, None
        target_low = (target or "").lower()
        if any(h in target_low for h in _REDIRECT_CHALLENGE_HINTS):
            return True, target
        if request is not None:
            req_host = self._host(request.url)
            resp_host = self._host(response.url)
            if req_host and resp_host and req_host != resp_host and any(
                h in target_low for h in ("challenge", "captcha", "verify")
            ):
                return True, target
        return False, None

    def _collect_markers(self, response: scrapy.http.Response) -> tuple[str, ...]:
        body = self._body_lower(response)
        markers: list[str] = []
        for marker in _CHALLENGE_MARKERS:
            if marker in body:
                markers.append(marker.decode("latin-1", errors="ignore"))
        return tuple(markers)

    def detect(
        self,
        response: scrapy.http.Response,
        *,
        request: scrapy.http.Request | None = None,
        empty_body_threshold: int = 256,
    ) -> CaptchaDetectionResult:
        base_signal = detect_ban_signal(
            response,
            request=request,
            empty_body_threshold=empty_body_threshold,
        )
        markers = self._collect_markers(response)
        suspicious_redirect, redirect_target = self._suspicious_redirect(request, response)
        signal = base_signal
        if signal is None and suspicious_redirect:
            signal = "captcha"
        if signal is None and markers and response.status in {200, 403, 429, 503}:
            signal = "captcha"
        return CaptchaDetectionResult(
            signal=signal,
            markers=markers,
            suspicious_redirect=suspicious_redirect,
            redirect_target=redirect_target,
        )


def build_captcha_solver(settings: Settings | None = None) -> CaptchaSolver:
    """Create captcha solver implementation from settings."""
    s = settings or app_settings
    backend = str(getattr(s, "SCRAPY_CAPTCHA_SOLVER_BACKEND", "noop") or "noop").strip().lower()
    if backend in {"", "noop", "none", "disabled"}:
        return NoopCaptchaSolver(reason="solver_not_configured")
    logger.warning("Unknown captcha solver backend '%s' - using noop solver", backend)
    return NoopCaptchaSolver(reason=f"unsupported_backend:{backend}")
