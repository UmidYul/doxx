from __future__ import annotations

from types import SimpleNamespace

import scrapy.http
from scrapy.http import HtmlResponse
from scrapy.settings import Settings as ScrapySettings

from config.settings import settings as app_settings
from infrastructure.access.captcha_hooks import (
    CaptchaDetectionResult,
    CaptchaSignalDetector,
    CaptchaSolveResult,
)
from infrastructure.middlewares.ratelimit_middleware import AccessAwareRateLimitMiddleware


class _SolverReturningRetry:
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
        _ = response, spider, detection, store, purpose
        nr = request.copy()
        nr.meta["from_solver"] = True
        return CaptchaSolveResult(
            handled=True,
            solver="noop",
            reason="test_retry",
            retry_request=nr,
            token=None,
            extra_meta={"captcha_solver_reason": "test_retry"},
        )


class _Spider:
    name = "mediapark"
    store_name = "mediapark"

    def __init__(self) -> None:
        self.settings = ScrapySettings({"DOWNLOAD_DELAY": 1.0, "DOWNLOAD_HANDLERS": {}})
        self.download_delay = 1.0


def _crawler() -> SimpleNamespace:
    return SimpleNamespace(engine=SimpleNamespace(downloader=SimpleNamespace(slots={})))


def test_captcha_solver_retry_request_is_returned(monkeypatch) -> None:
    monkeypatch.setattr(app_settings, "SCRAPY_CAPTCHA_HOOKS_ENABLED", True)
    monkeypatch.setattr(app_settings, "SCRAPY_CAPTCHA_MAX_SOLVE_ATTEMPTS", 1)
    monkeypatch.setattr(app_settings, "SCRAPY_RANDOMIZED_DELAY_ENABLED", False)
    monkeypatch.setattr(
        "infrastructure.middlewares.ratelimit_middleware.is_feature_enabled",
        lambda feature_name, store_name=None, entity_key=None, **kwargs: feature_name == "captcha_hooks",
    )

    req = scrapy.http.Request(
        "https://shop.uz/p/1",
        meta={"store_name": "mediapark", "access_purpose": "product", "prior_failures": 0},
    )
    resp = HtmlResponse(
        url=req.url,
        request=req,
        body=b"<html><div class='g-recaptcha'></div></html>",
        encoding="utf-8",
    )
    mw = AccessAwareRateLimitMiddleware(
        _crawler(),
        captcha_detector=CaptchaSignalDetector(),
        captcha_solver=_SolverReturningRetry(),
    )
    spider = _Spider()

    out = mw.process_response(req, resp, spider)

    assert isinstance(out, scrapy.http.Request)
    assert out.meta.get("from_solver") is True
    assert out.meta.get("captcha_solver_attempts") == 1
    assert out.meta.get("captcha_solver_name") == "noop"
    assert out.meta.get("captcha_solver_reason") == "test_retry"
