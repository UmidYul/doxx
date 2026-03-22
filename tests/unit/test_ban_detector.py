from __future__ import annotations

import orjson
import scrapy.http
from scrapy.http import HtmlResponse, TextResponse

from infrastructure.access import ban_detector


def _req(url: str = "https://shop.uz/cat") -> scrapy.http.Request:
    return scrapy.http.Request(url)


def test_thin_json_not_empty_shell():
    body = orjson.dumps({"items": [], "total": 0})
    resp = TextResponse(
        url="https://api.shop.uz/v1/items",
        body=body,
        encoding="utf-8",
        headers={b"Content-Type": b"application/json; charset=utf-8"},
    )
    assert ban_detector.is_empty_shell(resp, empty_body_threshold=500) is False
    assert ban_detector.detect_ban_signal(resp, empty_body_threshold=500) is None


def test_cloudflare_challenge_detected():
    body = b"<html><title>Just a moment</title><script></script></html>"
    resp = HtmlResponse(url="https://x.uz/", body=body, encoding="utf-8")
    assert ban_detector.detect_ban_signal(resp, request=_req(), empty_body_threshold=400) == "cloudflare_challenge"


def test_captcha_detected():
    body = b"<html><div class='g-recaptcha'></div></html>"
    resp = HtmlResponse(url="https://x.uz/", body=body, encoding="utf-8")
    assert ban_detector.is_captcha_page(resp) is True
    sig = ban_detector.detect_ban_signal(resp, request=_req(), empty_body_threshold=400)
    assert sig == "captcha"


def test_js_shell_detected():
    body = (
        b"<!doctype html><html><head></head><body>"
        b"<script></script><script></script><script></script>"
        b"<div id='__next'></div></body></html>"
    )
    resp = HtmlResponse(url="https://x.uz/", body=body, encoding="utf-8")
    assert ban_detector.is_js_shell(resp) is True


def test_small_html_with_visible_text_not_auto_block():
    body = b"<html><body><h1>OK</h1><p>Some real text content here for catalog.</p></body></html>"
    resp = HtmlResponse(url="https://x.uz/", body=body, encoding="utf-8")
    assert ban_detector.is_empty_shell(resp, empty_body_threshold=500) is False


def test_mobile_trap_signal():
    req = scrapy.http.Request("https://shop.uz/p")
    resp = TextResponse(url="https://m.shop.uz/p", body=b"{}", encoding="utf-8")
    assert ban_detector.is_mobile_trap(req, resp) is True
    assert ban_detector.detect_ban_signal(resp, request=req, empty_body_threshold=400) == "mobile_redirect"
