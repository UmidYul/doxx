from __future__ import annotations

import scrapy.http
from scrapy.http import HtmlResponse, TextResponse

from config.settings import Settings
from infrastructure.access.captcha_hooks import (
    CaptchaSignalDetector,
    NoopCaptchaSolver,
    build_captcha_solver,
)


def _req(url: str = "https://shop.uz/catalog") -> scrapy.http.Request:
    return scrapy.http.Request(url)


def test_detector_captcha_marker_detected() -> None:
    req = _req("https://shop.uz/p/1")
    resp = HtmlResponse(
        url=req.url,
        request=req,
        body=b"<html><div class='g-recaptcha'></div></html>",
        encoding="utf-8",
    )
    detector = CaptchaSignalDetector(suspicious_redirect_enabled=True)

    res = detector.detect(resp, request=req, empty_body_threshold=256)

    assert res.signal == "captcha"
    assert res.is_captcha_related() is True
    assert any("recaptcha" in marker for marker in res.markers)


def test_detector_suspicious_redirect_promoted_to_captcha() -> None:
    req = _req("https://shop.uz/catalog")
    resp = TextResponse(
        url=req.url,
        request=req,
        status=302,
        headers={b"Location": b"/captcha?next=/catalog"},
        body=b"",
        encoding="utf-8",
    )
    detector = CaptchaSignalDetector(suspicious_redirect_enabled=True)

    res = detector.detect(resp, request=req, empty_body_threshold=256)

    assert res.signal == "captcha"
    assert res.suspicious_redirect is True
    assert res.redirect_target is not None


def test_noop_solver_returns_graceful_result() -> None:
    req = _req("https://shop.uz/p/1")
    resp = HtmlResponse(url=req.url, request=req, body=b"<html></html>", encoding="utf-8")
    detector = CaptchaSignalDetector()
    detection = detector.detect(resp, request=req, empty_body_threshold=256)
    solver = NoopCaptchaSolver()

    result = solver.solve(
        req,
        resp,
        spider=None,
        detection=detection,
        store="shop",
        purpose="product",
    )

    assert result.handled is False
    assert result.solver == "noop"
    assert result.retry_request is None


def test_build_captcha_solver_unknown_backend_falls_back_to_noop() -> None:
    s = Settings(SCRAPY_CAPTCHA_SOLVER_BACKEND="unknown_backend", _env_file=None)

    solver = build_captcha_solver(s)

    assert isinstance(solver, NoopCaptchaSolver)
