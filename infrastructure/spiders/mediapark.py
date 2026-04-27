from __future__ import annotations

import json
import re
from typing import Any, Iterator
from urllib.parse import urljoin, urlsplit, urlunsplit

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
_TECH_CATEGORY_SLUGS: frozenset[str] = frozenset(
    {
        "smartfon",
        "smartfony",
        "telefon",
        "telefony",
        "smartfony-po-brendu",
        "noutbuk",
        "noutbuki",
        "ultrabuk",
        "planshet",
        "planshety",
        "tablet",
        "televizor",
        "televizory",
        "tv",
        "monitor",
        "smart-chasy",
        "gadzhety",
    }
)
_LOW_VALUE_CATEGORY_SLUGS: frozenset[str] = frozenset(
    {
        "telefony-17",
        "telefonlar-17",
        "2-sim-karty",
        "smartfon-v-rassrochku",
        "smartfony-telefony-planshety-i-gadzhety",
    }
)
_PRODUCT_URL_RE = re.compile(r"https?://[^/]+/products/view/[^/?#]+", re.I)
_PRODUCT_PATH_RE = re.compile(r"/products/view/[a-z0-9-]+-\d+", re.I)
_CATEGORY_URL_RE = re.compile(r"https?://[^/]+/products/category/[^\"'\s<>]+", re.I)
_SITEMAP_LOC_RE = re.compile(r"<loc>\s*(https?://[^<\s]+)\s*</loc>", re.I)
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
_SITEMAP_DETAIL_RE = re.compile(r"/product-view/\d+/detailed\.xml$", re.I)
_MEDIAPARK_LOCATION_SLUGS: frozenset[str] = frozenset(
    {
        "tashkent",
        "jizzakh",
        "namangan",
        "samarkand",
        "surxondaryo",
        "sirdaryo",
        "fergana",
        "khorezm",
        "navoiy",
        "qashqadaryo",
        "karakalpakstan",
        "bukhara",
        "andijan",
    }
)
_PRODUCT_DETAIL_SUFFIXES: tuple[str, ...] = ("/characteristics", "/feedback", "/shops")


class MediaparkSpider(BaseProductSpider):
    name = "mediapark"
    store_name = "mediapark"
    allowed_domains = ["mediapark.uz", "www.mediapark.uz"]
    product_sitemap_index_url = "https://mediapark.uz/product-view/products.xml"
    _MAX_CATEGORY_PAGES = 12
    _MAX_EMPTY_OR_DUP_STREAK = 2
    _SYNTHETIC_NEXT_MIN_PRODUCT_LINKS = 24
    category_url_map = {
        "phone": ("https://mediapark.uz/products/category/telefony-17/smartfony-40",),
        "laptop": ("https://mediapark.uz/products/category/noutbuki-i-ultrabuki-22/noutbuki-313",),
        "tv": ("https://mediapark.uz/products/category/televizory-i-smart-televizory-8/televizory-307",),
        "accessory": ("https://mediapark.uz/products/category/gadzhety-18/smart-chasy-51",),
    }
    brand_category_url_map = {
        ("phone", "apple"): ("https://mediapark.uz/products/category/smartfony-po-brendu-660/smartfony-apple-iphone-211",),
        ("phone", "samsung"): ("https://mediapark.uz/products/category/smartfony-po-brendu-660/smartfony-samsung-210",),
    }

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
        return self.target_start_category_urls((
            "https://mediapark.uz/products/category/telefony-17/smartfony-40",
            "https://mediapark.uz/products/category/noutbuki-i-ultrabuki-22/noutbuki-313",
            "https://mediapark.uz/products/category/televizory-i-smart-televizory-8/televizory-307",
            "https://mediapark.uz/products/category/gadzhety-18/smart-chasy-51",
        ))

    def start_requests(self):
        discovery_mode = self._discovery_mode()
        if discovery_mode in {"sitemap", "hybrid"}:
            self.crawl_registry.categories_started_total += 1
            self._crawl_event(
                "CATEGORY_START",
                category_url=self.product_sitemap_index_url,
                page=1,
                discovery_mode=discovery_mode,
            )
            req = self.schedule_safe_request(
                self.product_sitemap_index_url,
                callback=self.parse_product_sitemap_index,
                purpose="listing",
                meta={
                    "category_url": self.product_sitemap_index_url,
                    "page": 1,
                    "empty_streak": 0,
                    "dup_sig_streak": 0,
                },
            )
            if req is not None:
                yield req
            if discovery_mode == "sitemap":
                return
        yield from super().start_requests()

    def is_product_page(self, response: scrapy.http.Response) -> bool:
        return "/products/view/" in response.url

    def canonicalize_product_url(self, url: str) -> str:
        canonical = super().canonicalize_product_url(url)
        parts = urlsplit(canonical)
        path = self._normalize_product_path(parts.path or "")
        return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))

    def extract_listing_product_urls(self, response: scrapy.http.Response) -> list[str]:
        return self._extract_product_links(response.text, base_url=response.url)

    def extract_listing_category_urls(self, response: scrapy.http.Response) -> list[str]:
        return self._extract_category_links(response.text, base_url=response.url, current_url=response.url)

    def extract_next_page_url(self, response: scrapy.http.Response) -> str | None:
        if response.url.lower().endswith(".xml"):
            return None
        product_links = self._extract_product_links(response.text, base_url=response.url)
        if not product_links:
            return None
        return self.extract_common_next_page_url(
            response,
            product_urls=product_links,
            min_product_links=self._SYNTHETIC_NEXT_MIN_PRODUCT_LINKS,
            path_markers=("/products/category/",),
        )

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

    def parse_product_sitemap_index(self, response: scrapy.http.Response):
        from infrastructure.access.resource_governance import release_request_governance_counters

        release_request_governance_counters(dict(response.meta or {}), self.store_name or self.name)
        detailed_sitemaps: list[str] = []
        seen: set[str] = set()
        for sitemap_url in self._extract_sitemap_locs(response.text):
            if not _SITEMAP_DETAIL_RE.search(sitemap_url):
                continue
            if sitemap_url in seen:
                continue
            seen.add(sitemap_url)
            detailed_sitemaps.append(sitemap_url)

        if not detailed_sitemaps:
            return

        first_url = detailed_sitemaps[0]
        self.crawl_registry.categories_started_total += 1
        self._crawl_event(
            "CATEGORY_DISCOVERED",
            parent_category_url=response.url,
            discovered_category_url=first_url,
            page=1,
        )
        req = self.schedule_safe_request(
            first_url,
            callback=self.parse_product_sitemap_leaf,
            purpose="product",
            priority=-20,
            meta={
                "category_url": first_url,
                "page": 1,
                "empty_streak": 0,
                "dup_sig_streak": 0,
                "sitemap_detailed_urls": detailed_sitemaps,
                "sitemap_leaf_index": 0,
                "sitemap_product_offset": 0,
            },
        )
        if req is not None:
            yield req

    def parse_product_sitemap_leaf(self, response: scrapy.http.Response):
        from infrastructure.access.resource_governance import release_request_governance_counters

        release_request_governance_counters(dict(response.meta or {}), self.store_name or self.name)
        reg = self.crawl_registry
        category_url = str(response.meta.get("category_url") or response.url)
        detailed_sitemaps = list(response.meta.get("sitemap_detailed_urls") or [response.url])
        leaf_index = int(response.meta.get("sitemap_leaf_index") or 0)
        offset = int(response.meta.get("sitemap_product_offset") or 0)

        product_urls = list(self._iter_root_product_urls_from_sitemap(response.text))
        if offset == 0:
            reg.remember_listing_page_url(response.url)
            reg.listing_pages_seen_total += 1
            extracted_count = len(product_urls)
            if extracted_count == 0:
                reg.record_zero_result_category(category_url)
            else:
                reg.record_category_with_results(category_url)
            reg.listing_cards_seen_total += extracted_count
            reg.record_listing_stats(listing_url=response.url, product_urls_found=extracted_count)
            self._crawl_event(
                "LISTING_PAGE",
                category_url=category_url,
                page=1,
                extracted_count=extracted_count,
                canonical_url=response.url,
                discovery_mode="sitemap_leaf",
            )

        page_seen_urls: set[str] = set()
        page_seen_source_ids: set[str] = set()
        batch_end = min(offset + self._sitemap_product_batch_size(), len(product_urls))
        next_offset = offset
        for index in range(offset, batch_end):
            product_url = product_urls[index]
            canonical_url = self.canonicalize_product_url(product_url)
            source_id = self.extract_source_id_from_url(canonical_url)
            reg.product_urls_seen_total += 1
            if canonical_url in page_seen_urls or (source_id and source_id in page_seen_source_ids):
                reg.product_urls_deduped_total += 1
                self._crawl_event(
                    "PRODUCT_DEDUPED",
                    category_url=category_url,
                    page=1,
                    canonical_url=canonical_url,
                    reason="sitemap_page_duplicate",
                )
                next_offset = index + 1
                continue
            if self.should_skip_product_url(canonical_url):
                reg.product_urls_deduped_total += 1
                self._crawl_event(
                    "PRODUCT_DEDUPED",
                    category_url=category_url,
                    page=1,
                    canonical_url=canonical_url,
                    reason="url_or_source_id_seen",
                )
                next_offset = index + 1
                continue
            req = self.schedule_safe_request(
                canonical_url,
                callback=self.parse,
                purpose="product",
                priority=20,
                meta={
                    "from_listing": response.url,
                    "category_url": category_url,
                },
            )
            if req is None:
                self._crawl_event(
                    "PRODUCT_SCHEDULE_BLOCKED",
                    category_url=category_url,
                    page=1,
                    canonical_url=canonical_url,
                    reason="resource_or_policy_gate",
                )
                break
            reg.remember_product_url(canonical_url)
            page_seen_urls.add(canonical_url)
            if source_id:
                reg.remember_source_id(source_id)
                page_seen_source_ids.add(source_id)
            next_offset = index + 1
            yield req

        if next_offset < len(product_urls):
            yield self._build_internal_sitemap_request(
                response.url,
                meta={
                    "category_url": category_url,
                    "page": 1,
                    "empty_streak": 0,
                    "dup_sig_streak": 0,
                    "sitemap_detailed_urls": detailed_sitemaps,
                    "sitemap_leaf_index": leaf_index,
                    "sitemap_product_offset": next_offset,
                },
            )
            return

        next_leaf_index = leaf_index + 1
        if next_leaf_index < len(detailed_sitemaps):
            next_leaf_url = str(detailed_sitemaps[next_leaf_index])
            self.crawl_registry.categories_started_total += 1
            self._crawl_event(
                "CATEGORY_DISCOVERED",
                parent_category_url=response.url,
                discovered_category_url=next_leaf_url,
                page=1,
            )
            req = self._build_internal_sitemap_request(
                next_leaf_url,
                meta={
                    "category_url": next_leaf_url,
                    "page": 1,
                    "empty_streak": 0,
                    "dup_sig_streak": 0,
                    "sitemap_detailed_urls": detailed_sitemaps,
                    "sitemap_leaf_index": next_leaf_index,
                    "sitemap_product_offset": 0,
                },
            )
            yield req
            return

        self._crawl_event(
            "PAGINATION_STOP",
            category_url=category_url,
            page=1,
            reason="sitemap_leaf_complete",
        )

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

        current_path = self._normalize_category_path(urlsplit(current_url).path)
        category_paths: set[str] = set()
        for candidate in candidates:
            clean = candidate.strip().strip('"').rstrip("\\").rstrip(",")
            absolute = urljoin(base_url, clean)
            parts = urlsplit(absolute)
            if "mediapark.uz" not in parts.netloc:
                continue
            path = self._normalize_category_path(parts.path)
            if not path or path == current_path or "/products/category/" not in path:
                continue
            lowered = path.lower()
            if any(slug in lowered for slug in _LOW_VALUE_CATEGORY_SLUGS):
                continue
            if not any(slug in lowered for slug in _TECH_CATEGORY_SLUGS):
                continue
            category_paths.add(path)
        return sorted(category_paths)

    @staticmethod
    def _normalize_category_path(path: str) -> str:
        clean = path.replace("\\", "/").rstrip("/")
        if clean.startswith("/ru/"):
            clean = clean[3:]
        elif clean.startswith("/uz/"):
            clean = clean[3:]
        return clean

    @staticmethod
    def _extract_sitemap_locs(xml_text: str) -> list[str]:
        return [match.strip() for match in _SITEMAP_LOC_RE.findall(xml_text) if match.strip()]

    @staticmethod
    def _normalize_product_path(path: str) -> str:
        clean = path.replace("\\", "/")
        if clean.startswith("/ru/"):
            clean = clean[3:]
        elif clean.startswith("/uz/"):
            clean = clean[3:]
        elif clean.startswith("/kr/"):
            clean = clean[3:]

        match = re.match(r"^/([^/]+)/products/view/(.+)$", clean, re.I)
        if match and match.group(1).lower() in _MEDIAPARK_LOCATION_SLUGS:
            clean = f"/products/view/{match.group(2)}"

        for suffix in _PRODUCT_DETAIL_SUFFIXES:
            if clean.lower().endswith(suffix):
                clean = clean[: -len(suffix)]
                break
        return clean

    def _iter_root_product_urls_from_sitemap(self, xml_text: str) -> Iterator[str]:
        seen: set[str] = set()
        for url in self._extract_sitemap_locs(xml_text):
            if "/products/view/" not in url.lower():
                continue
            canonical = self.canonicalize_product_url(url)
            if canonical in seen:
                continue
            seen.add(canonical)
            yield canonical

    @staticmethod
    def _sitemap_product_batch_size() -> int:
        return 5

    def _build_internal_sitemap_request(
        self,
        url: str,
        *,
        meta: dict[str, Any],
        priority: int = -20,
    ) -> scrapy.Request:
        from infrastructure.access.header_profiles import build_desktop_headers
        from infrastructure.access.request_strategy import build_request_meta

        req_meta = {
            **meta,
            **build_request_meta(
                self.store_name or self.name,
                "product",
                spider_supports_browser=self._supports_playwright(),
                record_mode_metrics=False,
                target_url=url,
            ),
        }
        headers = build_desktop_headers(
            self.store_name or self.name,
            "product",
            request_url=url,
        )
        return scrapy.Request(
            url,
            callback=self.parse_product_sitemap_leaf,
            errback=self.errback_default,
            meta=req_meta,
            headers=headers,
            priority=priority,
            dont_filter=True,
        )

    def _discovery_mode(self) -> str:
        if self.has_crawl_targeting():
            return "categories"
        raw = str(getattr(self, "discovery_mode", "sitemap") or "sitemap").strip().lower()
        if raw in {"sitemap", "categories", "hybrid"}:
            return raw
        return "sitemap"

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
