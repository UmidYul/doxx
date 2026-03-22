from __future__ import annotations

# Centralized desktop client hints for Uzbekistan-facing storefronts.
_DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def build_desktop_headers(
    store_name: str,
    purpose: str,
    *,
    referer: str | None = None,
) -> dict[str, str]:
    """Build deterministic HTTP headers (no per-middleware random UA)."""
    _ = store_name  # reserved for per-store overrides later
    headers: dict[str, str] = {
        "User-Agent": _DESKTOP_UA,
        "Accept-Language": "ru-RU,ru;q=0.9,uz-UZ,uz;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    if purpose == "api":
        headers["Accept"] = "application/json, text/plain, */*"

    if referer:
        headers["Referer"] = referer
    elif purpose == "product":
        # Encourage category → PDP continuity when caller did not pass referer
        headers.setdefault(
            "Sec-Fetch-Dest", "document"
        )
        headers.setdefault("Sec-Fetch-Mode", "navigate")
    return headers
