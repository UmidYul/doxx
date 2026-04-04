from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import scrapy.http

from infrastructure.spiders.base import BaseProductSpider
from infrastructure.spiders.product_classifier import classify_category, extract_brand

_PRODUCT_PATH_RE = re.compile(r"/(?:ru|uz)/moderated-offer/[^/?#]+", re.I)
_PRODUCT_HREF_RE = re.compile(r'["\'](/(?:ru|uz)/moderated-offer/[^"\']+)["\']', re.I)
_PRODUCT_ESCAPED_HREF_RE = re.compile(r"\\/(?:ru|uz)\\/moderated-offer\\/[^\"'\\s]+", re.I)
_CATEGORY_HREF_RE = re.compile(r'["\'](/(?:ru|uz)/categories/[^"\']+)["\']', re.I)
_ID_IN_PATH_RE = re.compile(r"-(\d{6,})(?:$|[/?#])")
_PRICE_NUM_RE = re.compile(r"(\d[\d\s\u00a0]{3,})")
_SUM_TEXT_RE = re.compile(r"(\d[\d\s\u00a0]{3,})\s*(?:сум|sum|so['\u2019]?m)", re.I)


_ALIFSHOP_SMARTPHONE_PREFIX = "/ru/categories/smartfoni-"
_ALIFSHOP_LOW_VALUE_CATEGORY_HINTS = (
    "/ru/categories/aksessuari-",
    "/ru/categories/chehli-",
    "/ru/categories/coputstvuyuschie-",
    "/ru/categories/smartfoni-i-gadzheti",
    "/ru/categories/smartfoni-i-telefoni",
)


class AlifshopSpider(BaseProductSpider):
    """Alifshop spider: category -> listing -> moderated-offer PDP with minimal structuring."""

    name = "alifshop"
    store_name = "alifshop"
    allowed_domains = ["alifshop.uz", "www.alifshop.uz"]

    custom_settings = {
        **BaseProductSpider.custom_settings,
        "DOWNLOAD_DELAY": 1.0,
        "RETRY_TIMES": 4,
        "DOWNLOAD_TIMEOUT": 60,
    }

    def start_category_urls(self) -> tuple[str, ...]:
        return (
            "https://alifshop.uz/ru/categories/smartfoni-apple",
            "https://alifshop.uz/ru/categories/smartfoni-samsung",
            "https://alifshop.uz/ru/categories/smartfoni-xiaomi",
            "https://alifshop.uz/ru/categories/smartfoni-honor",
            "https://alifshop.uz/ru/categories/smartfoni-tecno",
        )

    def is_product_page(self, response: scrapy.http.Response) -> bool:
        return bool(_PRODUCT_PATH_RE.search(urlparse(response.url).path))

    def canonicalize_product_url(self, url: str) -> str:
        parsed = urlparse(url)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))

    def extract_listing_product_urls(self, response: scrapy.http.Response) -> list[str]:
        candidates: list[str] = []
        for href in response.css('a[href*="/moderated-offer/"]::attr(href)').getall():
            if not href:
                continue
            full = response.urljoin(href.strip())
            parsed = urlparse(full)
            if "alifshop.uz" not in parsed.netloc or not _PRODUCT_PATH_RE.search(parsed.path):
                continue
            candidates.append(full)

        text = response.text
        if not candidates:
            for href in _PRODUCT_HREF_RE.findall(text):
                full = response.urljoin(href.strip())
                parsed = urlparse(full)
                if "alifshop.uz" in parsed.netloc and _PRODUCT_PATH_RE.search(parsed.path):
                    candidates.append(full)
        if not candidates:
            for href in _PRODUCT_ESCAPED_HREF_RE.findall(text):
                full = response.urljoin(href.replace("\\/", "/").strip())
                parsed = urlparse(full)
                if "alifshop.uz" in parsed.netloc and _PRODUCT_PATH_RE.search(parsed.path):
                    candidates.append(full)

        seen: set[str] = set()
        out: list[str] = []
        for url in candidates:
            canonical = self.canonicalize_product_url(url)
            if canonical in seen:
                continue
            seen.add(canonical)
            out.append(canonical)
        return out

    def extract_listing_category_urls(self, response: scrapy.http.Response) -> list[str]:
        candidates: list[str] = []
        for href in response.css('a[href*="/categories/"]::attr(href)').getall():
            if not href:
                continue
            full = response.urljoin(href.strip())
            parsed = urlparse(full)
            if "alifshop.uz" not in parsed.netloc:
                continue
            path = parsed.path.rstrip("/")
            if _PRODUCT_PATH_RE.search(path):
                continue
            if "/categories/" not in path:
                continue
            candidates.append(full)

        if not candidates:
            for href in _CATEGORY_HREF_RE.findall(response.text):
                full = response.urljoin(href.strip())
                parsed = urlparse(full)
                path = parsed.path.rstrip("/")
                if "alifshop.uz" in parsed.netloc and "/categories/" in path and not _PRODUCT_PATH_RE.search(path):
                    candidates.append(full)

        current = urlparse(response.url).path.rstrip("/")
        seen: set[str] = set()
        out: list[str] = []
        for url in candidates:
            path = urlparse(url).path.rstrip("/")
            if not path or path == current or path in seen:
                continue
            path_lower = path.lower()
            if any(low_value in path_lower for low_value in _ALIFSHOP_LOW_VALUE_CATEGORY_HINTS):
                continue
            if not path_lower.startswith(_ALIFSHOP_SMARTPHONE_PREFIX):
                continue
            seen.add(path)
            out.append(path)
        return sorted(out)

    def extract_next_page_url(self, response: scrapy.http.Response) -> str | None:
        next_href = (
            response.css('a[rel="next"]::attr(href)').get()
            or response.css('link[rel="next"]::attr(href)').get()
            or response.css('a[aria-label*="next"]::attr(href), a[aria-label*="Next"]::attr(href)').get()
        )
        if next_href:
            return response.urljoin(next_href)

        if not self.extract_listing_product_urls(response):
            return None

        parsed = urlparse(response.url)
        query = parse_qs(parsed.query)
        page = int(query.get("page", ["1"])[0] or "1")
        query["page"] = [str(page + 1)]
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", urlencode({k: v[0] for k, v in query.items()}), ""))

    def extract_source_id_from_url(self, url: str) -> str | None:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        for key in ("offerId", "offer_id", "productId", "product_id", "id", "sku"):
            value = query.get(key)
            if value and value[0].strip():
                return value[0].strip()
        match = _ID_IN_PATH_RE.search(parsed.path + "/")
        if match:
            return match.group(1)
        tail = parsed.path.rstrip("/").rsplit("/", 1)[-1].strip()
        return tail or None

    def full_parse_item(self, response: scrapy.http.Response) -> dict[str, Any] | None:
        if not self.is_product_page(response):
            return None
        title = self._extract_title(response)
        source_id = self.extract_source_id_from_url(response.url)
        if not title or not source_id:
            return None
        brand = extract_brand(title)
        return {
            "url": response.url,
            "title": title,
            "name": title,
            "source_id": source_id,
            "external_id": source_id,
            "source": self.store_name,
            "price_str": self._extract_price_str(response),
            "in_stock": self._extract_in_stock(response),
            "brand": brand,
            "description": self._extract_description(response),
            "raw_specs": self._extract_raw_specs(response),
            "image_urls": self._extract_image_urls(response),
            "category_hint": self.extract_category_hint(response, title),
            "external_ids": {"alifshop": source_id},
        }

    def extract_category_hint(
        self,
        response_or_url: scrapy.http.Response | str,
        title: str | None = None,
    ) -> str | None:
        url = response_or_url.url if hasattr(response_or_url, "url") else str(response_or_url)
        return classify_category(url, title or "")

    def _extract_title(self, response: scrapy.http.Response) -> str:
        candidates = [
            response.css("h1::text").get(),
            response.css('meta[property="og:title"]::attr(content)').get(),
            response.css("title::text").get(),
        ]
        for value in candidates:
            text = self._clean_text(value)
            if not text:
                continue
            text = re.sub(r"^\s*SMARTUP\s*-\s*(Купить|Цена и характеристики)\s*", "", text, flags=re.I)
            text = re.sub(r"\s+онлайн с доставкой.*$", "", text, flags=re.I)
            text = re.sub(r"\s+в маркетплейсе alifshop\.uz.*$", "", text, flags=re.I)
            text = text.strip(" -")
            if text:
                return text
        return ""

    def _extract_price_str(self, response: scrapy.http.Response) -> str:
        for sel in (
            'meta[property="product:price:amount"]::attr(content)',
            'meta[property="og:price:amount"]::attr(content)',
        ):
            raw = self._clean_text(response.css(sel).get())
            if raw and raw.isdigit():
                return f"{raw} сум"

        for txt in response.css("body *::text").getall():
            cleaned = self._clean_text(txt)
            if not cleaned:
                continue
            match = _SUM_TEXT_RE.search(cleaned)
            if match:
                digits = re.sub(r"[^\d]", "", match.group(1))
                if digits:
                    return f"{digits} сум"
        return ""

    def _extract_in_stock(self, response: scrapy.http.Response) -> bool:
        for sel in (
            'meta[property="product:availability"]::attr(content)',
            'meta[name="product:availability"]::attr(content)',
        ):
            availability = self._clean_text(response.css(sel).get()).lower()
            if availability:
                return "out of stock" not in availability and "нет в наличии" not in availability
        text = response.text.lower()
        return "нет в наличии" not in text and "out of stock" not in text

    def _extract_description(self, response: scrapy.http.Response) -> str:
        return self._clean_text(response.css('meta[name="description"]::attr(content)').get())

    def _extract_image_urls(self, response: scrapy.http.Response) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()

        def add(value: str) -> None:
            url = response.urljoin((value or "").strip())
            if not url or url in seen or url.startswith("data:"):
                return
            if url.endswith((".svg", ".ico")):
                return
            seen.add(url)
            out.append(url)

        for sel in (
            'meta[property="og:image"]::attr(content)',
            'meta[name="twitter:image"]::attr(content)',
        ):
            value = response.css(sel).get()
            if value:
                add(value)

        normalized = response.text.replace("\\/", "/")
        for value in re.findall(r"https?://s3\.fortifai\.uz/shop/moderation/[^\"'\s<>]+", normalized, flags=re.I):
            add(value)

        for attr in ("src", "data-src", "srcset"):
            for value in response.css(f"img::attr({attr})").getall():
                if not value:
                    continue
                part = value.split(",")[0].strip().split(" ")[0]
                add(part)
        return out

    def _extract_raw_specs(self, response: scrapy.http.Response) -> dict[str, Any]:
        normalized = response.text.replace("\\/", "/")
        specs: dict[str, Any] = {}

        row_patterns = (
            re.compile(
                r'<p[^>]*max-w-\[320px\][^>]*>(?P<key>.*?)</p>\s*<div[^>]*whitespace-break-spaces[^>]*>(?P<value>.*?)</div>',
                flags=re.I | re.S,
            ),
            re.compile(
                r'<div[^>]*border-b[^>]*>\s*<div[^>]*>\s*<p[^>]*>(?P<key>.*?)</p>\s*<div[^>]*whitespace-break-spaces[^>]*>(?P<value>.*?)</div>',
                flags=re.I | re.S,
            ),
        )
        for pattern in row_patterns:
            for match in pattern.finditer(normalized):
                key = self._strip_html(match.group("key"))
                value = self._strip_html(match.group("value"))
                if not key or not value or len(key) > 140 or len(value) > 320:
                    continue
                specs.setdefault(key, value)

        if specs:
            return specs

        # Text fallback for pages where the specs block is rendered without stable CSS hooks.
        lines = [self._clean_text(value) for value in response.css("body *::text").getall()]
        lines = [line for line in lines if line]
        try:
            start = next(i for i, line in enumerate(lines) if line.lower() == "характеристики")
        except StopIteration:
            start = -1
        if start >= 0:
            body_lines = lines[start + 1 :]
            for index in range(0, len(body_lines) - 1, 2):
                key = body_lines[index]
                value = body_lines[index + 1]
                if key.lower() in {"характеристики", "общие характеристики", "отзывы"}:
                    continue
                if len(key) > 140 or len(value) > 320:
                    continue
                specs.setdefault(key, value)
        return specs

    def _clean_text(self, value: object) -> str:
        text = html.unescape(str(value or ""))
        text = text.replace("\u00a0", " ")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _strip_html(self, raw: str) -> str:
        text = re.sub(r"<[^>]+>", " ", str(raw))
        return self._clean_text(text)
