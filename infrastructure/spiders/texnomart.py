from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import scrapy.http

from infrastructure.spiders.base import BaseProductSpider
from infrastructure.spiders.product_classifier import classify_category, extract_brand as _classify_brand

_PRODUCT_PATH_RE = re.compile(
    r"/(?:ru/)?(?:(?:[a-z0-9-]+/)?product(?:/detail)?|catalog/product|katalog/product)/",
    re.I,
)
_PRODUCT_HREF_TEXT_RE = re.compile(
    r'["\'](/(?:ru/)?(?:(?:[a-z0-9-]+/)?product(?:/detail)?|catalog/product|katalog/product)/[^"\']+)["\']',
    re.I,
)
_ID_IN_PATH_RE = re.compile(r"-(\d{4,})(?:$|[/?#])")
_ID_QUERY_RE = ("sku", "skuId", "product_id", "id")
_PRICE_NUM_RE = re.compile(r"(\d[\d\s]{2,})")
_SUM_TEXT_RE = re.compile(r"[^<]{0,40}\d[\d\s]{2,}[^<]{0,20}(?:сум|sum|so'm)", re.I)
_PLAYWRIGHT_HANDLER = "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler"


class TexnomartSpider(BaseProductSpider):
    _LISTING_PATH_RE = re.compile(r"^/(?:ru/)?katalog/[a-z0-9%+\-_/]+$", re.I)

    """Texnomart spider: listing -> PDP with lightweight extraction."""

    name = "texnomart"
    store_name = "texnomart"
    allowed_domains = ["texnomart.uz", "www.texnomart.uz"]

    custom_settings = {
        **BaseProductSpider.custom_settings,
        "DOWNLOAD_DELAY": 1.0,
        "DOWNLOAD_HANDLERS": {
            "https": _PLAYWRIGHT_HANDLER,
            "http": _PLAYWRIGHT_HANDLER,
        },
        "PLAYWRIGHT_BROWSER_TYPE": "chromium",
        "PLAYWRIGHT_LAUNCH_OPTIONS": {"headless": True},
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 90_000,
        "PLAYWRIGHT_MAX_PAGES_PER_CONTEXT": 2,
        "RETRY_TIMES": 4,
        "DOWNLOAD_TIMEOUT": 90,
    }

    def start_category_urls(self) -> tuple[str, ...]:
        # Phase 1: phones only.
        return (
            "https://texnomart.uz/ru/katalog/smartfony/",
        )

    def is_product_page(self, response: scrapy.http.Response) -> bool:
        return bool(_PRODUCT_PATH_RE.search(urlparse(response.url).path))

    def extract_listing_product_urls(self, response: scrapy.http.Response) -> list[str]:
        candidates: list[str] = []
        for href in response.css('a[href*="/product/"]::attr(href), a[href*="/catalog/product/"]::attr(href)').getall():
            if not href:
                continue
            full = response.urljoin(href.strip())
            parsed = urlparse(full)
            if "texnomart.uz" not in parsed.netloc:
                continue
            if not _PRODUCT_PATH_RE.search(parsed.path):
                continue
            candidates.append(full)

        if not candidates:
            for href in _PRODUCT_HREF_TEXT_RE.findall(response.text):
                full = response.urljoin(href.strip())
                parsed = urlparse(full)
                if "texnomart.uz" in parsed.netloc and _PRODUCT_PATH_RE.search(parsed.path):
                    candidates.append(full)

        seen: set[str] = set()
        out: list[str] = []
        for url in candidates:
            if url in seen:
                continue
            seen.add(url)
            out.append(url)
        return out

    def extract_listing_category_urls(self, response: scrapy.http.Response) -> list[str]:
        candidates: list[str] = []
        for href in response.css(
            'a[href*="/catalog/"]::attr(href), a[href*="/katalog/"]::attr(href), a[href*="/category/"]::attr(href)'
        ).getall():
            if not href:
                continue
            full = response.urljoin(href.strip())
            parsed = urlparse(full)
            if "texnomart.uz" not in parsed.netloc:
                continue
            path = parsed.path.rstrip("/")
            if "/catalog/" not in path and "/katalog/" not in path and "/category/" not in path:
                continue
            if _PRODUCT_PATH_RE.search(path):
                continue
            if not self._LISTING_PATH_RE.match(path):
                continue
            candidates.append(full)

        text = response.text
        for href in re.findall(r'["\'](/(?:ru/)?(?:catalog|katalog|category)/[^"\']+)["\']', text, re.I):
            full = response.urljoin(href.strip())
            parsed = urlparse(full)
            path = parsed.path.rstrip("/")
            if (
                "texnomart.uz" in parsed.netloc
                and not _PRODUCT_PATH_RE.search(path)
                and self._LISTING_PATH_RE.match(path)
            ):
                candidates.append(full)

        # Phase 1: only follow subcategory links related to phones
        _phone_slugs = ("smartfon", "telefon", "phone")
        current = urlparse(response.url).path.rstrip("/")
        seen: set[str] = set()
        out: list[str] = []
        for url in candidates:
            p = urlparse(url)
            path = p.path.rstrip("/")
            if not path or path == current:
                continue
            if path in seen:
                continue
            path_lower = path.lower()
            if not any(slug in path_lower for slug in _phone_slugs):
                continue
            seen.add(path)
            out.append(path)
        return sorted(out)

    def extract_next_page_url(self, response: scrapy.http.Response) -> str | None:
        next_href = (
            response.css('a[rel="next"]::attr(href)').get()
            or response.css('link[rel="next"]::attr(href)').get()
            or response.css('a[aria-label*="Next"]::attr(href), a[aria-label*="next"]::attr(href)').get()
        )
        if next_href:
            return response.urljoin(next_href)

        if not self.extract_listing_product_urls(response):
            return None
        parsed = urlparse(response.url)
        if "/catalog/" not in parsed.path:
            return None
        query = parse_qs(parsed.query)
        page = int(query.get("page", ["1"])[0] or "1")
        query["page"] = [str(page + 1)]
        new_query = urlencode({k: v[0] for k, v in query.items()})
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", new_query, ""))

    def extract_source_id_from_url(self, url: str) -> str | None:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        for key in _ID_QUERY_RE:
            val = query.get(key)
            if val and val[0].strip():
                return f"{key}:{val[0].strip()}"
        match = _ID_IN_PATH_RE.search(parsed.path + "/")
        if match:
            return f"p:{match.group(1)}"
        tail = parsed.path.rstrip("/").rsplit("/", 1)[-1].strip()
        return tail or None

    def full_parse_item(self, response: scrapy.http.Response) -> dict[str, Any] | None:
        if not self.is_product_page(response):
            return None
        product_ld = self._extract_product_ld(response)
        title = self._extract_title(response, product_ld)
        source_id = self._source_id_from_ld(product_ld) or self.extract_source_id_from_url(response.url)
        if not title or not source_id:
            return None
        return {
            "url": response.url,
            "title": title,
            "name": title,
            "source_id": source_id,
            "external_id": source_id,
            "source": self.store_name,
            "price_str": self._extract_price_str(response, product_ld),
            "in_stock": self._extract_in_stock(response, product_ld),
            "brand": self._extract_brand(title, product_ld),
            "description": self._extract_description(response, product_ld),
            "raw_specs": self._extract_raw_specs(response, product_ld),
            "image_urls": self._extract_image_urls(response, product_ld),
            "category_hint": self.extract_category_hint(response, title),
        }

    def extract_category_hint(
        self,
        response_or_url: scrapy.http.Response | str,
        title: str | None = None,
    ) -> str | None:
        url = response_or_url.url if hasattr(response_or_url, "url") else str(response_or_url)
        return classify_category(url, title or "")

    def _extract_product_ld(self, response: scrapy.http.Response) -> dict[str, Any] | None:
        blocks = response.css('script[type="application/ld+json"]::text').getall()
        for raw in blocks:
            payload = (raw or "").strip()
            if not payload:
                continue
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                continue
            found = self._pick_product_node(data)
            if found is not None:
                return found
        return None

    def _pick_product_node(self, data: Any) -> dict[str, Any] | None:
        if isinstance(data, dict):
            if str(data.get("@type", "")).lower() == "product":
                return data
            graph = data.get("@graph")
            if isinstance(graph, list):
                for node in graph:
                    if isinstance(node, dict) and str(node.get("@type", "")).lower() == "product":
                        return node
        if isinstance(data, list):
            for node in data:
                if isinstance(node, dict) and str(node.get("@type", "")).lower() == "product":
                    return node
        return None

    def _extract_title(self, response: scrapy.http.Response, product_ld: dict[str, Any] | None) -> str:
        candidates = [
            (product_ld or {}).get("name"),
            response.css("h1::text").get(),
            response.css('meta[property="og:title"]::attr(content)').get(),
            response.css("title::text").get(),
        ]
        for value in candidates:
            text = re.sub(r"\s+", " ", str(value or "")).strip()
            if text:
                return text
        return ""

    _MIN_PLAUSIBLE_UZS = 100_000

    def _digits_from_price_text(self, text: str | None) -> str | None:
        if not text:
            return None
        digits = re.sub(r"[^\d]", "", text)
        if not digits.isdigit():
            return None
        if int(digits) < self._MIN_PLAUSIBLE_UZS:
            return None
        return digits

    def _extract_price_str(self, response: scrapy.http.Response, product_ld: dict[str, Any] | None) -> str:
        # 1) Main PDP price block — full retail price (not .chip-price installment)
        for block_sel in (
            ".product__price",
            ".product-price-current",
        ):
            blob = response.css(block_sel).xpath("string(.)").get()
            d = self._digits_from_price_text(blob)
            if d:
                return f"{d} сум"

        offers = (product_ld or {}).get("offers")
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        if isinstance(offers, dict):
            price = offers.get("price")
            if price not in (None, ""):
                try:
                    pv = int(float(str(price).replace(" ", "")))
                    if pv >= self._MIN_PLAUSIBLE_UZS:
                        return f"{str(price).strip()} сум"
                except (ValueError, TypeError):
                    pass

        # 2) Lines mentioning "сум" / sum — prefer largest plausible (main price vs chips)
        candidates: list[int] = []
        for txt in response.css("main *::text, article *::text").getall():
            cleaned = re.sub(r"\s+", " ", (txt or "")).strip()
            if not any(x in cleaned.lower() for x in ("сум", "sum", "so'm")):
                continue
            match = _PRICE_NUM_RE.search(cleaned)
            if match:
                digits = re.sub(r"\s+", "", match.group(1))
                if digits.isdigit() and int(digits) >= self._MIN_PLAUSIBLE_UZS:
                    candidates.append(int(digits))
        if candidates:
            return f"{max(candidates)} сум"

        frag = _SUM_TEXT_RE.search(response.text)
        if frag:
            cleaned = re.sub(r"\s+", " ", frag.group(0)).strip()
            match = _PRICE_NUM_RE.search(cleaned)
            if match:
                digits = re.sub(r"\s+", "", match.group(1))
                if digits.isdigit() and int(digits) >= self._MIN_PLAUSIBLE_UZS:
                    return f"{digits} сум"
        return ""

    def _extract_in_stock(self, response: scrapy.http.Response, product_ld: dict[str, Any] | None) -> bool:
        offers = (product_ld or {}).get("offers")
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        if isinstance(offers, dict):
            availability = str(offers.get("availability") or "").lower()
            if availability:
                return "outofstock" not in availability and "discontinued" not in availability
        text = response.text.lower()
        return "нет в наличии" not in text and "out of stock" not in text

    def _extract_image_urls(self, response: scrapy.http.Response, product_ld: dict[str, Any] | None) -> list[str]:
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

        raw_img = (product_ld or {}).get("image")
        if isinstance(raw_img, str):
            add(raw_img)
        elif isinstance(raw_img, list):
            for item in raw_img:
                if isinstance(item, str):
                    add(item)
                elif isinstance(item, dict) and isinstance(item.get("url"), str):
                    add(str(item["url"]))
        for attr in ("src", "data-src", "srcset"):
            for value in response.css(f"img::attr({attr})").getall():
                if not value:
                    continue
                part = value.split(",")[0].strip().split(" ")[0]
                add(part)
        return out

    def _extract_brand(self, title: str, product_ld: dict[str, Any] | None) -> str:
        raw = (product_ld or {}).get("brand")
        ld_brand: str | None = None
        if isinstance(raw, dict):
            ld_brand = str(raw.get("name") or "").strip() or None
        elif isinstance(raw, str):
            ld_brand = raw.strip() or None
        return _classify_brand(title, ld_brand)

    def _extract_description(self, response: scrapy.http.Response, product_ld: dict[str, Any] | None) -> str:
        ld_desc = re.sub(r"\s+", " ", str((product_ld or {}).get("description") or "")).strip()
        if ld_desc:
            return ld_desc
        return re.sub(
            r"\s+",
            " ",
            str(response.css('meta[name="description"]::attr(content)').get() or ""),
        ).strip()

    def _extract_raw_specs(self, response: scrapy.http.Response, product_ld: dict[str, Any] | None) -> dict[str, Any]:
        specs: dict[str, Any] = {}
        props = (product_ld or {}).get("additionalProperty")
        if isinstance(props, list):
            for entry in props:
                if not isinstance(entry, dict):
                    continue
                key = re.sub(r"\s+", " ", str(entry.get("name") or "")).strip()
                val = re.sub(r"\s+", " ", str(entry.get("value") or "")).strip()
                if key and val and key not in specs:
                    specs[key] = val

        for row in response.css("main table tr, article table tr, .product table tr"):
            cells = [x.strip() for x in row.css("td, th").xpath("string(.)").getall() if x.strip()]
            if len(cells) < 2:
                continue
            key = re.sub(r"\s+", " ", cells[0]).strip()
            val = re.sub(r"\s+", " ", cells[1]).strip()
            if key and val and len(key) < 120 and key not in specs:
                specs[key] = val

        for dl in response.css("main dl, article dl, .product dl"):
            for dt in dl.css("dt"):
                key = re.sub(r"\s+", " ", str(dt.xpath("string(.)").get() or "")).strip()
                dd = dt.xpath("following-sibling::dd[1]")
                if not dd:
                    continue
                val = re.sub(r"\s+", " ", str(dd.xpath("string(.)").get() or "")).strip()
                if key and val and len(key) < 120 and key not in specs:
                    specs[key] = val

        for row in response.css('[class*="characteristic"] li, [class*="spec"] li, [class*="property"] li'):
            parts = [re.sub(r"\s+", " ", p).strip() for p in row.css("*::text").getall() if p.strip()]
            if len(parts) >= 2:
                key, val = parts[0], parts[-1]
                if key and val and len(key) < 120 and key not in specs:
                    specs[key] = val
        return specs

    def _source_id_from_ld(self, product_ld: dict[str, Any] | None) -> str | None:
        sku = str((product_ld or {}).get("sku") or "").strip()
        if sku:
            return f"sku:{sku}"
        product_id = str((product_ld or {}).get("productID") or "").strip()
        if product_id:
            return product_id
        return None
