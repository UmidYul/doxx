from __future__ import annotations

import re
from typing import Any

# HTML/XML page flow — reject obvious binary downloads as "page" content
_SUSPICIOUS_CT_PREFIXES = (
    "application/octet-stream",
    "application/x-msdownload",
    "application/zip",
    "application/x-zip",
    "application/pdf",
    "application/x-tar",
    "application/gzip",
    "application/java-archive",
    "application/vnd.",
    "audio/",
    "video/",
)


def is_suspicious_content_type(content_type: str | None) -> bool:
    if not content_type:
        return False
    ct = content_type.split(";")[0].strip().lower()
    return any(ct.startswith(p) for p in _SUSPICIOUS_CT_PREFIXES)


def is_unexpected_attachment(response: Any) -> bool:
    """Heuristic: Content-Disposition attachment + non-HTML type."""
    try:
        headers = getattr(response, "headers", None)
        if headers is None:
            return False
        cd = headers.get("Content-Disposition") or headers.get(b"Content-Disposition")
        if isinstance(cd, bytes):
            cd = cd.decode("utf-8", errors="replace")
        cd = (cd or "").lower()
        if "attachment" not in cd:
            return False
        ct = headers.get("Content-Type") or headers.get(b"Content-Type")
        if isinstance(ct, bytes):
            ct = ct.decode("utf-8", errors="replace")
        if not ct:
            return True
        base = ct.split(";")[0].strip().lower()
        if base in ("text/html", "application/xhtml+xml", "text/xml", "application/xml"):
            return False
        return True
    except Exception:
        return False


def should_download_response(response: Any) -> bool:
    """
    True if response looks like a normal crawlable HTML document.
    False if it looks like a binary/attachment that should not be parsed as listing/PDP.
    """
    try:
        headers = getattr(response, "headers", None)
        if headers is None:
            return True
        ct = headers.get("Content-Type") or headers.get(b"Content-Type")
        if isinstance(ct, bytes):
            ct = ct.decode("utf-8", errors="replace")
        ct_s = ct or ""
        if is_suspicious_content_type(ct_s):
            return False
        if is_unexpected_attachment(response):
            return False
        base = ct_s.split(";")[0].strip().lower() if ct_s else ""
        if not base or base in ("text/html", "application/xhtml+xml"):
            return True
        if base.startswith("text/"):
            return True
        return False
    except Exception:
        return True
