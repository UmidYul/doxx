from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from config.settings import settings

_SENSITIVE_HEADER_NAMES = frozenset(
    {
        "x-parser-key",
        "x-request-signature",
        "authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "proxy-authorization",
    }
)

# Keys that look like credentials but are business identifiers
_PAYLOAD_KEY_ALLOWLIST = frozenset(
    {
        "entity_key",
        "payload_hash",
        "event_id",
        "batch_id",
        "request_idempotency_key",
        "source_id",
        "category_hint",
    }
)


def _is_sensitive_payload_key(key: str) -> bool:
    kl = key.lower()
    if kl in _PAYLOAD_KEY_ALLOWLIST:
        return False
    if kl in ("secret", "token", "signature", "password", "parser_key", "api_key", "access_token", "refresh_token"):
        return True
    if kl == "key" or kl.endswith("_secret") or kl.endswith("_token") or kl.endswith("_password"):
        return True
    if "signature" in kl and kl != "payload_hash":
        return True
    return False


def redact_headers(headers: dict[str, object]) -> dict[str, object]:
    if not getattr(settings, "MASK_SENSITIVE_HEADERS_IN_LOGS", True):
        return dict(headers)
    out: dict[str, object] = {}
    for k, v in headers.items():
        lk = str(k).lower()
        if lk in _SENSITIVE_HEADER_NAMES or lk.startswith("x-parser-"):
            out[k] = "[REDACTED]"
        else:
            out[k] = v
    return out


def redact_payload(payload: dict[str, object]) -> dict[str, object]:
    if not getattr(settings, "MASK_SENSITIVE_FIELDS_IN_LOGS", True):
        return dict(payload)
    return _redact_obj(payload)  # type: ignore[return-value]


def _redact_obj(obj: object) -> object:
    if isinstance(obj, dict):
        out: dict[str, object] = {}
        for k, v in obj.items():
            sk = str(k)
            if _is_sensitive_payload_key(sk):
                out[sk] = "[REDACTED]"
            else:
                out[sk] = _redact_obj(v)
        return out
    if isinstance(obj, list):
        return [_redact_obj(x) for x in obj]
    return obj


def minimize_url_for_support(url: str, *, full_query_allowed: bool = False) -> str:
    """
    Strip sensitive query params; optionally drop entire query for support/export surfaces.
    Host + path kept for triage when ``full_query_allowed`` is False (default).
    """
    if not url:
        return url
    try:
        parts = urlsplit(url.strip())
        if full_query_allowed:
            return redact_url(url)
        # Default: no query string in support outputs unless explicitly allowed.
        if not parts.query:
            return url
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment))
    except Exception:
        return url


def redact_url(url: str) -> str:
    if not getattr(settings, "MASK_SENSITIVE_HEADERS_IN_LOGS", True):
        return url
    try:
        parts = urlsplit(url)
        if not parts.query:
            return url
        pairs = parse_qsl(parts.query, keep_blank_values=True)
        sensitive_params = frozenset({"token", "key", "signature", "secret", "password", "access_token", "api_key"})
        new_pairs: list[tuple[str, str]] = []
        for k, v in pairs:
            if k.lower() in sensitive_params or any(x in k.lower() for x in ("secret", "token", "password")):
                new_pairs.append((k, "[REDACTED]"))
            else:
                new_pairs.append((k, v))
        new_query = urlencode(new_pairs)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))
    except Exception:
        return url


_SENSITIVE_MSG_PATTERNS = (
    (re.compile(r"(?i)(x-parser-key|x-request-signature|authorization:\s*)\S+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(bearer\s+)[\w\-._~+/]+=*"), r"\1[REDACTED]"),
)


def redact_exception_message(message: str) -> str:
    if not getattr(settings, "MASK_SENSITIVE_FIELDS_IN_LOGS", True):
        return message
    s = message
    for pat, repl in _SENSITIVE_MSG_PATTERNS:
        s = pat.sub(repl, s)
    return redact_url(s)


def redact_mapping_for_logs(obj: dict[str, Any] | None) -> dict[str, Any]:
    """Typed helper for log ``details`` / metrics dicts."""
    if not obj:
        return {}
    redacted = redact_payload({str(k): v for k, v in obj.items()})
    return dict(redacted)
