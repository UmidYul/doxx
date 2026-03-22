from __future__ import annotations

import pytest

from infrastructure.spiders import url_tools


def test_strip_tracking_params_removes_utm_and_fbclid():
    u = "https://shop.uz/p/1?utm_source=x&fbclid=abc&page=2&gclid=z"
    s = url_tools.strip_tracking_params(u)
    assert "utm_" not in s
    assert "fbclid" not in s
    assert "gclid" not in s
    assert "page=2" in s


def test_normalize_mobile_host_m_prefix():
    u = "https://m.shop.uz/products/1"
    assert url_tools.normalize_mobile_host(u) == "https://shop.uz/products/1"


def test_canonicalize_url_mobile_and_tracking():
    left = "https://m.example.com/item/5/?utm_campaign=1"
    right = "https://example.com/item/5"
    assert url_tools.is_same_product_url(left, right)


def test_is_same_product_url_trailing_slash():
    assert url_tools.is_same_product_url(
        "https://x.uz/a/b/",
        "https://x.uz/a/b",
    )


def test_openstat_stripped():
    u = "https://x.uz/p?openstat=foo"
    assert "openstat" not in url_tools.strip_tracking_params(u).lower()
