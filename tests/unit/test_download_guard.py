from __future__ import annotations

import scrapy.http
from scrapy.http import HtmlResponse

from infrastructure.security.download_guard import (
    is_suspicious_content_type,
    is_unexpected_attachment,
    should_download_response,
)


def test_suspicious_octet_stream() -> None:
    assert is_suspicious_content_type("application/octet-stream")
    assert is_suspicious_content_type("application/zip; charset=binary")


def test_html_not_suspicious() -> None:
    assert not is_suspicious_content_type("text/html; charset=utf-8")


def test_should_download_rejects_binary_content_type() -> None:
    resp = HtmlResponse(
        url="https://mediapark.uz/x",
        body=b"x",
        encoding="utf-8",
        headers={b"Content-Type": b"application/pdf"},
    )
    assert not should_download_response(resp)


def test_attachment_non_html_blocked() -> None:
    resp = scrapy.http.Response(
        url="https://mediapark.uz/x",
        body=b"x",
        headers={
            b"Content-Disposition": b'attachment; filename="f.zip"',
            b"Content-Type": b"application/zip",
        },
    )
    assert is_unexpected_attachment(resp)
    assert not should_download_response(resp)


def test_plain_html_response_ok() -> None:
    resp = HtmlResponse(
        url="https://mediapark.uz/x",
        body=b"<html></html>",
        encoding="utf-8",
        headers={b"Content-Type": b"text/html"},
    )
    assert should_download_response(resp)
