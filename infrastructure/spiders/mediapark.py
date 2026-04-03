from __future__ import annotations

import json
import re
from typing import Any, Iterator
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import scrapy

from infrastructure.spiders.base import BaseProductSpider
from infrastructure.spiders.product_classifier import classify_category, extract_brand

_PLAYWRIGHT_HANDLER = "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler"

_SPEC_SECTION_TITLES: tuple[str, ...] = (
    "Характеристики",
    "Технические характеристики",
    "Characteristics",
    "Specifications",
    "Specs",
)
_SPEC_STOP_MARKERS: frozenset[str] = frozenset(
    {
        "Наличие в магазинах",
        "Отзывы",
        "Описание",
        "Похожие товары",
        "Все товары",
        "Reviews",
        "Description",
    }
)
_PHONE_CATEGORY_SLUGS: frozenset[str] = frozenset(
    {
        "smartfon",
        "smartfony",
        "telefon",
        "telefony",
        "smartfony-po-brendu",
    }
)
_PRODUCT_URL_RE = re.compile(r"https?://[^/]+/products/view/[^/?#]+", re.I)
_PRODUCT_PATH_RE = re.compile(r"/products/view/[a-z0-9-]+-\d+", re.I)
_CATEGORY_URL_RE = re.compile(r"https?://[^/]+/products/category/[^\"'\s<>]+", re.I)
_STOCK_OUT_PATTERNS = re.compile(
    r"нет\s+в\s+наличии|недоступен\s+к\s+заказу|товар\s+не\s+найден|страница\s+не\s+найдена|out\s+of\s+stock|schema\.org/OutOfStock",
    re.I,
)
_SOFT_404_PATTERNS = re.compile(
    r"товар\s+не\s+найден|страница\s+не\s+найдена|404\s+not\s+found|product\s+not\s+found",
    re.I,
)
_RSC_SPEC_PAIR_RE = re.compile(
    r'"name"\s*:\s*\{\s*"uz"\s*:\s*"[^"]*"\s*,\s*"ru"\s*:\s*"([^"]+)"\s*,\s*"kr"\s*:\s*"[^"]*"\s*\}\s*,\s*'
    r'"choices"\s*:\s*\[\s*\{\s*"id"\s*:\s*"[^"]+"\s*,\s*"name"\s*:\s*\{\s*"uz"\s*:\s*"[^"]*"\s*,\s*"ru"\s*:\s*"([^"]+)"',
    re.DOTALL,
)


class MediaparkSpider(BaseProductSpider):
    name = "mediapark"
    store_name = "mediapark"
    allowed_domains = ["mediapark.uz", "www.mediapark.uz"]
    _MAX_CATEGORY_PAGES = 12
    _MAX_EMPTY_OR_DUP_STREAK = 2

    custom_settings = {
        **BaseProductSpider.custom_settings,
        "DOWNLOAD_DELAY": 1.0,
        "DOWNLOAD_TIMEOUT": 90,
        "RETRY_TIMES": 4,
        "DOWNLOAD_HANDLERS": {
            "https": _PLAYWRIGHT_HANDLER,
            "http": _PLAYWRIGHT_HANDLER,
        },
        "PLAYWRIGHT_BROWSER_TYPE": "chromium",
        "PLAYWRIGHT_LAUNCH_OPTIONS": {"headless": True},
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 90_000,
        "PLAYWRIGHT_MAX_PAGES_PER_CONTEXT": 2,
    }

    def start_category_urls(self) -> tuple[str, ...]:
        return (
            "https://mediapark.uz/products/category/telefony-17/smartfony-40",
            "https://mediapark.uz/products/category/smartfony-po-brendu-660/smartfony-samsung-210",
            "https://mediapark.uz/products/category/smartfony-po-brendu-660/smartfony-huawei-363",
            "https://mediapark.uz/products/category/smartfony-po-brendu-660/smartfony-apple-iphone-211",
        )

    def is_product_page(self, response: scrapy.http.Response) -> bool:
        return "/products/view/" in response.url

    def extract_listing_product_urls(self, response: scrapy.http.Response) -> list[str]:
        return self._extract_product_links(response.text, base_url=response.url)

    def extract_listing_category_urls(self, response: scrapy.http.Response) -> list[str]:
        return self._extract_category_links(response.text, base_url=response.url, current_url=response.url)

    def extract_next_page_url(self, response: scrapy.http.Response) -> str | None:
        if not self._extract_product_links(response.text, base_url=response.url):
            return None
        current_page = self._page_number(response.url)
        return self._build_paginated_url(response.url, current_page + 1)

    def should_stop_pagination(
        self,
        *,
        next_url: str | None,
        page: int,
        empty_streak: int,
        dup_sig_streak: int,
    ) -> tuple[bool, str]:
        if not next_url:
            return True, "no_next_url"
        if page >= self._MAX_CATEGORY_PAGES:
            return True, "mediapark_max_pages"
        if empty_streak >= self._MAX_EMPTY_OR_DUP_STREAK:
            return True, "mediapark_empty_repeats"
        if dup_sig_streak >= self._MAX_EMPTY_OR_DUP_STREAK:
            return True, "mediapark_duplicate_listing_repeats"
        return False, ""

    def extract_source_id_from_url(self, url: str) -> str | None:
        source_id = self._extract_external_id(url)
        return source_id or None

    def extract_category_hint(
        self,
        response_or_url: scrapy.http.Response | str,
        title: str | None = None,
    ) -> str | None:
        url = response_or_url.url if hasattr(response_or_url, "url") else str(response_or_url)
        ld_category = None
        if isinstance(response_or_url, scrapy.http.Response):
            ld_category = self._extract_ld_category(self._parse_product_ld(response_or_url) or {})
        return classify_category(url, title or "", ld_category)

    def full_parse_item(self, response: scrapy.http.Response) -> dict[str, Any] | None:
        product_schema = self._parse_product_ld(response) or {}
        if response.status >= 400:
            return None
        if self._looks_like_missing_product(response) and not product_schema:
            return None

        source_id = self._extract_external_id(response.url)
        title = self._extract_title(product_schema, response) or source_id or ""
        if not title:
            return None

        price_raw = self._extract_price_text(product_schema, response)
        in_stock = self._extract_in_stock(product_schema, response)
        description = self._extract_description(product_schema, response)
        raw_specs = self._merge_specs(
            self._specs_from_rsc(response),
            self._specs_from_next_data(response),
            self._specs_from_product_schema(product_schema),
            self._specs_from_tables(response),
            self._specs_from_body_text(response),
        )
        image_urls = self._extract_images(product_schema, response)
        category_hint = self.extract_category_hint(response, title)
        brand = self._extract_brand(title, product_schema)

        external_ids = {"mediapark": source_id} if source_id else {}
        return {
            "source": self.store_name,
            "url": response.url,
            "source_id": source_id,
            "external_id": source_id,
            "title": title,
            "name": title,
            "brand": brand,
            "price_str": price_raw,
            "in_stock": in_stock,
            "description": description,
            "raw_specs": raw_specs,
            "image_urls": image_urls,
            "category_hint": category_hint,
            "external_ids": external_ids,
        }

    @staticmethod
    def _extract_product_links(html: str, *, base_url: str) -> list[str]:
        normalized_html = html.replace("\\/", "/")
        candidates = re.findall(
            r'(https?://[^"\'\s<>]*/products/view/[^"\'\s<>]+|/products/view/[^"\'\s<>]+)',
            normalized_html,
        )
        links: set[str] = set()
        for candidate in candidates:
            clean = candidate.strip().strip('"').rstrip("\\").rstrip(",")
            absolute = urljoin(base_url, clean)
            if _PRODUCT_URL_RE.fullmatch(absolute):
                links.add(absolute.split("?", 1)[0])
        return sorted(links)

    def _extract_category_links(self, html: str, *, base_url: str, current_url: str) -> list[str]:
        normalized_html = html.replace("\\/", "/")
        candidates = re.findall(
            r'(https?://[^"\'\s<>]*/products/category/[^"\'\s<>]+|/products/category/[^"\'\s<>]+)',
            normalized_html,
        )
        candidates.extend(_CATEGORY_URL_RE.findall(normalized_html))

        current_path = urlsplit(current_url).path.rstrip("/")
        category_paths: set[str] = set()
        for candidate in candidates:
            clean = candidate.strip().strip('"').rstrip("\\").rstrip(",")
            absolute = urljoin(base_url, clean)
            parts = urlsplit(absolute)
            if "mediapark.uz" not in parts.netloc:
                continue
            path = parts.path.rstrip("/")
            if not path or path == current_path or "/products/category/" not in path:
                continue
            lowered = path.lower()
            if not any(slug in lowered for slug in _PHONE_CATEGORY_SLUGS):
                continue
            category_paths.add(path)
        return sorted(category_paths)

    @staticmethod
    def _build_paginated_url(category_url: str, page: int) -> str:
        if page <= 1:
            return category_url
        parts = urlsplit(category_url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["page"] = str(page)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    @staticmethod
    def _page_number(url: str) -> int:
        query = dict(parse_qsl(urlsplit(url).query, keep_blank_values=True))
        raw = str(query.get("page") or "").strip()
        return int(raw) if raw.isdigit() else 1

    @staticmethod
    def _looks_like_missing_product(response: scrapy.http.Response) -> bool:
        if response.status >= 400:
            return True
        visible_html = re.sub(r"<script\b[^>]*>[\s\S]*?</script>", " ", response.text, flags=re.I)
        visible_html = re.sub(r"<style\b[^>]*>[\s\S]*?</style>", " ", visible_html, flags=re.I)
        body_text = re.sub(r"\s+", " ", visible_html.replace("\xa0", " ")).strip()
        return bool(_SOFT_404_PATTERNS.search(body_text))

    @staticmethod
    def _parse_product_ld(response: scrapy.http.Response) -> dict[str, Any] | None:
        blocks = re.findall(
            r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>',
            response.text,
            re.I,
        )
        for raw_json in blocks:
            raw_json = raw_json.strip()
            if not raw_json:
                continue
            try:
                payload = json.loads(raw_json)
            except json.JSONDecodeError:
                continue
            product = MediaparkSpider._pick_product_node(payload)
            if product is not None:
                return product
        return None

    @staticmethod
    def _pick_product_node(payload: Any) -> dict[str, Any] | None:
        if isinstance(payload, dict):
            if str(payload.get("@type") or "").lower() == "product":
                return payload
            graph = payload.get("@graph")
            if isinstance(graph, list):
                for node in graph:
                    if isinstance(node, dict) and str(node.get("@type") or "").lower() == "product":
                        return node
        if isinstance(payload, list):
            for node in payload:
                if isinstance(node, dict) and str(node.get("@type") or "").lower() == "product":
                    return node
        return None

    @staticmethod
    def _extract_ld_category(product_schema: dict[str, Any]) -> str | None:
        for key in ("category", "categoryName"):
            value = product_schema.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        breadcrumb = product_schema.get("breadcrumb")
        if isinstance(breadcrumb, str) and breadcrumb.strip():
            return breadcrumb.strip()
        return None

    @staticmethod
    def _extract_title(product_schema: dict[str, Any], response: scrapy.http.Response) -> str | None:
        name = product_schema.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
        og_title = response.css("meta[property='og:title']::attr(content)").get()
        if og_title:
            title = og_title.strip()
            if " | " in title:
                title = title.split(" | ", 1)[0].strip()
            if title:
                return title
        h1 = response.css("h1::text").get()
        return h1.strip() if h1 and h1.strip() else None

    @staticmethod
    def _extract_price_text(product_schema: dict[str, Any], response: scrapy.http.Response) -> str:
        offers = MediaparkSpider._pick_offer_node(product_schema.get("offers"))
        if isinstance(offers, dict):
            price = offers.get("price")
            normalized = MediaparkSpider._normalize_price_string(price)
            if normalized:
                return normalized

        meta_price = response.css("meta[property='product:price:amount']::attr(content)").get()
        normalized_meta = MediaparkSpider._normalize_price_string(meta_price)
        if normalized_meta:
            return normalized_meta

        match = re.search(r'"price"\s*:\s*"?([0-9][0-9\s.,]*)"?', response.text, re.I)
        if match:
            return MediaparkSpider._normalize_price_string(match.group(1))
        return ""

    @staticmethod
    def _pick_offer_node(offers: Any) -> dict[str, Any] | None:
        if isinstance(offers, dict):
            return offers
        if isinstance(offers, list) and offers:
            return offers[0] if isinstance(offers[0], dict) else None
        return None

    @staticmethod
    def _normalize_price_string(raw: object) -> str:
        if raw is None:
            return ""
        text = re.sub(r"\s+", " ", str(raw)).strip()
        digits = re.sub(r"[^\d]", "", text)
        return digits or text

    @staticmethod
    def _extract_in_stock(product_schema: dict[str, Any], response: scrapy.http.Response) -> bool:
        offers = MediaparkSpider._pick_offer_node(product_schema.get("offers"))
        availability = str((offers or {}).get("availability") or "").lower()
        in_stock = "outofstock" not in availability and "discontinued" not in availability
        if _STOCK_OUT_PATTERNS.search(response.text):
            return False
        return in_stock

    @staticmethod
    def _extract_description(product_schema: dict[str, Any], response: scrapy.http.Response) -> str:
        description = product_schema.get("description")
        if isinstance(description, str) and description.strip():
            return re.sub(r"\s+", " ", description.replace("\xa0", " ")).strip()
        meta_description = response.css("meta[name='description']::attr(content)").get()
        if meta_description and meta_description.strip():
            return re.sub(r"\s+", " ", meta_description.replace("\xa0", " ")).strip()
        paragraphs = [
            re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
            for text in response.css("p::text").getall()
            if text and text.strip()
        ]
        return paragraphs[0] if paragraphs else ""

    def _extract_images(self, product_schema: dict[str, Any], response: scrapy.http.Response) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []

        def add(raw_url: str | None) -> None:
            if not raw_url:
                return
            absolute = response.urljoin(raw_url.strip())
            if not absolute or absolute in seen:
                return
            lowered = absolute.lower()
            if lowered.startswith("data:") or lowered.endswith((".svg", ".ico")):
                return
            if "mediapark.uz" not in lowered and "/img/" not in lowered and "/imgs/" not in lowered and "/static/" not in lowered:
                return
            seen.add(absolute)
            ordered.append(absolute)

        raw_images = product_schema.get("image")
        if isinstance(raw_images, str):
            add(raw_images)
        elif isinstance(raw_images, list):
            for image in raw_images:
                if isinstance(image, str):
                    add(image)

        next_data = self._parse_next_data(response)
        for image in self._collect_image_candidates(next_data):
            add(image)

        for attr in ("data-src", "data-lazy-src", "data-original", "src"):
            for image in response.css(f"img::attr({attr})").getall():
                add(image)

        og_image = response.css("meta[property='og:image']::attr(content)").get()
        add(og_image)
        return ordered

    @staticmethod
    def _extract_brand(title: str, product_schema: dict[str, Any]) -> str:
        raw_brand = product_schema.get("brand")
        ld_brand: str | None = None
        if isinstance(raw_brand, dict):
            ld_brand = str(raw_brand.get("name") or "").strip() or None
        elif isinstance(raw_brand, str):
            ld_brand = raw_brand.strip() or None
        return extract_brand(title, ld_brand)

    @staticmethod
    def _extract_external_id(url: str) -> str:
        path = urlsplit(url).path.rstrip("/")
        tail = path.rsplit("/", 1)[-1]
        match = re.search(r"-(\d+)$", tail)
        if match:
            return match.group(1)
        digits = re.search(r"/(\d+)(?:$|/)", path)
        if digits:
            return digits.group(1)
        return tail

    def _specs_from_rsc(self, response: scrapy.http.Response) -> dict[str, str]:
        blob = self._next_f_blob(response)
        specs: dict[str, str] = {}
        for label, value in _RSC_SPEC_PAIR_RE.findall(blob):
            clean_label = self._clean_spec_text(label)
            clean_value = self._clean_spec_text(value)
            if self._is_reasonable_spec_pair(clean_label, clean_value):
                specs.setdefault(clean_label, clean_value)
        return specs

    @staticmethod
    def _next_f_blob(response: scrapy.http.Response) -> str:
        chunks = re.findall(r'self\.__next_f\.push\(\[1,"([\s\S]*?)"\]\)', response.text)
        parts: list[str] = []
        for chunk in chunks:
            parts.append(
                chunk.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
            )
        return "\n".join(parts)

    def _specs_from_next_data(self, response: scrapy.http.Response) -> dict[str, str]:
        payload = self._parse_next_data(response)
        specs: dict[str, str] = {}
        for label, value in self._iter_named_values(payload):
            clean_label = self._clean_spec_text(label)
            clean_value = self._clean_spec_text(value)
            if self._is_reasonable_spec_pair(clean_label, clean_value):
                specs.setdefault(clean_label, clean_value)
        return specs

    @staticmethod
    def _parse_next_data(response: scrapy.http.Response) -> dict[str, Any]:
        script = response.xpath("//script[@id='__NEXT_DATA__']/text()").get()
        if not script:
            return {}
        try:
            payload = json.loads(script)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _iter_named_values(self, payload: Any) -> Iterator[tuple[str, str]]:
        if isinstance(payload, dict):
            name = self._text_from_value(payload.get("name"))
            value = self._text_from_value(payload.get("value"))
            if name and value:
                yield name, value

            if name and isinstance(payload.get("choices"), list):
                choice_values = [
                    self._text_from_value(choice.get("name") if isinstance(choice, dict) else choice)
                    for choice in payload["choices"]
                ]
                joined = ", ".join(v for v in choice_values if v)
                if joined:
                    yield name, joined

            for child in payload.values():
                yield from self._iter_named_values(child)
        elif isinstance(payload, list):
            for child in payload:
                yield from self._iter_named_values(child)

    def _specs_from_product_schema(self, product_schema: dict[str, Any]) -> dict[str, str]:
        specs: dict[str, str] = {}
        additional = product_schema.get("additionalProperty")
        if not isinstance(additional, list):
            return specs
        for entry in additional:
            if not isinstance(entry, dict):
                continue
            label = self._clean_spec_text(entry.get("name"))
            value = self._clean_spec_text(entry.get("value"))
            if self._is_reasonable_spec_pair(label, value):
                specs.setdefault(label, value)
        return specs

    def _specs_from_tables(self, response: scrapy.http.Response) -> dict[str, str]:
        specs: dict[str, str] = {}
        for row in response.css("table tr"):
            cells = [
                self._clean_spec_text(text)
                for text in row.css("td, th").xpath("string(.)").getall()
                if self._clean_spec_text(text)
            ]
            if len(cells) < 2:
                continue
            label, value = cells[0], cells[1]
            if self._is_reasonable_spec_pair(label, value):
                specs.setdefault(label, value)
        return specs

    def _specs_from_body_text(self, response: scrapy.http.Response) -> dict[str, str]:
        text = "\n".join(
            self._clean_spec_text(chunk)
            for chunk in response.xpath("//body//text()").getall()
            if self._clean_spec_text(chunk)
        )
        return self._parse_specs_from_page_text(text)

    @staticmethod
    def _parse_specs_from_page_text(text: str) -> dict[str, str]:
        lines = [
            re.sub(r"\s+", " ", line.replace("\xa0", " ")).strip()
            for line in text.splitlines()
            if line and line.strip()
        ]
        if not lines:
            return {}

        section_titles = {title.lower() for title in _SPEC_SECTION_TITLES}
        stop_markers = {marker.lower() for marker in _SPEC_STOP_MARKERS}
        indices = [index for index, line in enumerate(lines) if line.rstrip(":").strip().lower() in section_titles]
        start = indices[-1] if indices else 0

        specs: dict[str, str] = {}
        index = start + 1 if indices else start
        while index < len(lines):
            line = lines[index]
            normalized = line.rstrip(":").strip().lower()
            if normalized in stop_markers and specs:
                break

            if line.endswith(":"):
                key = line[:-1].strip()
                value = ""
                if index + 1 < len(lines):
                    nxt = lines[index + 1].strip()
                    if nxt and not nxt.endswith(":") and nxt.rstrip(":").strip().lower() not in stop_markers:
                        value = nxt
                        index += 1
                if MediaparkSpider._is_reasonable_spec_pair(key, value):
                    specs.setdefault(key, value)
            elif ":" in line and len(line) < 220:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()
                if MediaparkSpider._is_reasonable_spec_pair(key, value):
                    specs.setdefault(key, value)
            else:
                dotted = re.match(r"^(.{2,90}?)(?:\s*[.\u00b7\u2022]{2,}\s*|\s{2,})(.{1,220})$", line)
                if dotted:
                    key = dotted.group(1).strip().rstrip(":")
                    value = dotted.group(2).strip()
                    if MediaparkSpider._is_reasonable_spec_pair(key, value):
                        specs.setdefault(key, value)
            index += 1

        return specs

    @staticmethod
    def _clean_spec_text(value: object) -> str:
        return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()

    @staticmethod
    def _is_reasonable_spec_pair(label: str, value: str) -> bool:
        if not label or not value:
            return False
        if len(label) > 90 or len(value) > 220:
            return False
        lowered = label.lower()
        return lowered not in {marker.lower() for marker in _SPEC_STOP_MARKERS}

    @classmethod
    def _merge_specs(cls, *sources: dict[str, str]) -> dict[str, str]:
        merged: dict[str, str] = {}
        for source in sources:
            for label, value in source.items():
                clean_label = cls._clean_spec_text(label)
                clean_value = cls._clean_spec_text(value)
                if cls._is_reasonable_spec_pair(clean_label, clean_value):
                    merged.setdefault(clean_label, clean_value)
        return merged

    def _text_from_value(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            clean = self._clean_spec_text(value)
            return clean or None
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, dict):
            for key in ("ru", "name", "title", "value", "label"):
                nested = self._text_from_value(value.get(key))
                if nested:
                    return nested
            return None
        if isinstance(value, list):
            parts = [self._text_from_value(item) for item in value]
            joined = ", ".join(part for part in parts if part)
            return joined or None
        return None

    def _collect_image_candidates(self, payload: Any) -> Iterator[str]:
        if isinstance(payload, dict):
            for key, value in payload.items():
                lowered = str(key).lower()
                if lowered in {"image", "images", "imageurl", "image_url"}:
                    text = self._text_from_value(value)
                    if text and ("/img/" in text or "/imgs/" in text or "mediapark.uz" in text):
                        yield text
                yield from self._collect_image_candidates(value)
        elif isinstance(payload, list):
            for item in payload:
                yield from self._collect_image_candidates(item)
