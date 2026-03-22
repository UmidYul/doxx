from __future__ import annotations

import re
from typing import Any

import scrapy.http

# Visible text heuristic: strip tags crudely for shell detection
_TAG_RE = re.compile(rb"<[^>]+>")
_WS_RE = re.compile(rb"\s+")

_CF_MARKERS = (
    b"cf-browser-verification",
    b"checking your browser",
    b"just a moment",
    b"cloudflare",
    b"cf-ray",
)
_CAPTCHA_MARKERS = (
    b"recaptcha",
    b"hcaptcha",
    b"g-recaptcha",
    b"captcha",
    b"showcaptcha",
)
_DENIED_MARKERS = (
    b"access denied",
    b"403 forbidden",
    b"forbidden",
    b"blocked",
    b"request blocked",
)


def _body_lower(response: scrapy.http.Response) -> bytes:
    return (response.body or b"").lower()


def _visible_text_len(response: scrapy.http.Response) -> int:
    raw = response.body or b""
    text = _TAG_RE.sub(b" ", raw)
    text = _WS_RE.sub(b" ", text).strip()
    return len(text)


def _content_type(response: scrapy.http.Response) -> str:
    h = response.headers.get(b"Content-Type", b"")
    return h.decode("latin-1", errors="ignore").split(";")[0].strip().lower()


def is_captcha_page(response: scrapy.http.Response) -> bool:
    b = _body_lower(response)
    return any(m in b for m in _CAPTCHA_MARKERS)


def is_block_page(response: scrapy.http.Response) -> bool:
    if response.status in (401, 403):
        return True
    if response.status >= 500:
        return True
    b = _body_lower(response)
    if any(m in b for m in _DENIED_MARKERS):
        return True
    return False


def is_js_shell(response: scrapy.http.Response) -> bool:
    """HTML with heavy JS bootstrap but almost no visible content (not JSON APIs)."""
    if response.status != 200:
        return False
    ct = _content_type(response)
    if "json" in ct:
        return False
    raw = response.body or b""
    if len(raw) < 80:
        return False
    low = raw.lower()
    if b"<html" not in low and b"<!doctype" not in low:
        return False
    script_tags = low.count(b"<script")
    visible = _visible_text_len(response)
    # Next/React/loader pages: many scripts, tiny visible text
    if script_tags >= 3 and visible < 120:
        if b"__next" in low or b"react" in low or b"webpack" in low or b"__nuxt" in low:
            return True
    if b"enable javascript" in low or b"javascript is required" in low:
        return True
    return False


def is_empty_shell(
    response: scrapy.http.Response,
    *,
    empty_body_threshold: int,
) -> bool:
    """Tiny HTML/unknown body without API JSON — likely shell or error, not a valid thin API."""
    if response.status != 200:
        return False
    ct = _content_type(response)
    if "json" in ct:
        return False
    raw = response.body or b""
    if len(raw) >= empty_body_threshold:
        return False
    if len(raw) == 0:
        return True
    low = raw.lower()
    if b"<html" in low or b"<!doctype" in low:
        visible = _visible_text_len(response)
        # Allow legitimate micro-HTML (e.g. redirect stub with refresh)
        if visible < 40 and b"refresh" not in low and b"location" not in low:
            return True
    return False


def is_mobile_trap(request: scrapy.http.Request, response: scrapy.http.Response) -> bool:
    try:
        rh = (response.url.split("/")[2] if "/" in response.url else "").lower()
        qh = (request.url.split("/")[2] if "/" in request.url else "").lower()
    except Exception:
        return False
    return rh.startswith("m.") and not qh.startswith("m.")


def is_transport_like_error_page(response: scrapy.http.Response) -> bool:
    if response.status in (502, 503, 504):
        return True
    if response.status != 200:
        return False
    ct = _content_type(response)
    if "html" not in ct and ct not in ("", "text/plain"):
        return False
    b = _body_lower(response)
    if any(x in b for x in (b"bad gateway", b"service unavailable", b"gateway time")):
        return True
    return False


def detect_ban_signal(
    response: scrapy.http.Response,
    *,
    request: scrapy.http.Request | None = None,
    empty_body_threshold: int = 256,
) -> str | None:
    """Return a single primary signal, or None if nothing conclusive."""
    if request and is_mobile_trap(request, response):
        return "mobile_redirect"

    if response.status == 403 and is_captcha_page(response):
        return "captcha"

    if any(m in _body_lower(response) for m in _CF_MARKERS) and response.status in (200, 403, 503):
        return "cloudflare_challenge"

    if is_captcha_page(response):
        return "captcha"

    if response.status == 403 and not is_captcha_page(response):
        return "access_denied"

    if is_transport_like_error_page(response):
        return "transport_like_error_page"

    if is_js_shell(response):
        return "js_shell"

    if is_empty_shell(response, empty_body_threshold=empty_body_threshold):
        return "empty_shell"

    return None
