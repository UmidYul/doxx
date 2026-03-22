from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Common tracking / marketing params to strip (deterministic crawl canonical form).
_TRACKING_EXACT: frozenset[str] = frozenset(
    {
        "fbclid",
        "gclid",
        "yclid",
        "openstat",
        "_openstat",
        "igshid",
        "mc_cid",
        "mc_eid",
        "mkt_tok",
        "si",
        "spm",
        "ved",
        "gs_lcp",
        "ref",
        "referrer",
        "fb_action_ids",
        "fb_action_types",
        "fb_source",
    }
)
_TRACKING_PREFIXES: tuple[str, ...] = ("utm_", "openstat_")


def _should_drop_query_key(key: str) -> bool:
    lk = (key or "").lower()
    if lk in _TRACKING_EXACT:
        return True
    return any(lk.startswith(p) for p in _TRACKING_PREFIXES)


def strip_tracking_params(url: str) -> str:
    """Remove known tracking query parameters; keep other query keys as-is."""
    p = urlparse(url.strip())
    if not p.query:
        return url.strip()
    pairs = parse_qsl(p.query, keep_blank_values=True)
    kept = [(k, v) for k, v in pairs if k and not _should_drop_query_key(k)]
    new_query = urlencode(kept, doseq=True)
    return urlunparse((p.scheme, p.netloc, p.path, p.params, new_query, p.fragment))


def normalize_trailing_slash(url: str) -> str:
    """Strip trailing slash except for bare origin path ``/``."""
    p = urlparse(url)
    path = p.path or ""
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return urlunparse((p.scheme, p.netloc, path, p.params, p.query, p.fragment))


def normalize_mobile_host(url: str) -> str:
    """Map common mobile host patterns to a desktop-style host when unambiguous."""
    p = urlparse(url)
    host = (p.netloc or "").lower()
    if not host:
        return url
    parts = host.split(".")
    if len(parts) >= 3 and parts[0] in ("m", "mobile", "touch"):
        new_netloc = ".".join(parts[1:])
        return urlunparse((p.scheme, new_netloc, p.path, p.params, p.query, p.fragment))
    if host.startswith("m.") and host.count(".") >= 2:
        new_netloc = host[2:]
        return urlunparse((p.scheme, new_netloc, p.path, p.params, p.query, p.fragment))
    return url


def canonicalize_url(url: str) -> str:
    """Deterministic URL form for crawl-layer dedupe: host, tracking, slash."""
    u = url.strip()
    u = normalize_mobile_host(u)
    p = urlparse(u)
    scheme = (p.scheme or "https").lower()
    netloc = (p.netloc or "").lower()
    path = p.path or ""
    if not path:
        path = "/"
    u2 = urlunparse((scheme, netloc, path, "", p.query, p.fragment))
    u2 = strip_tracking_params(u2)
    u2 = normalize_trailing_slash(u2)
    return u2


def canonicalize_product_url(url: str) -> str:
    """Default PDP canonicalization — same as general canonical for 2A."""
    return canonicalize_url(url)


def is_same_product_url(left: str, right: str) -> bool:
    return canonicalize_product_url(left) == canonicalize_product_url(right)
