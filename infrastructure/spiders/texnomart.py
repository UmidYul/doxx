from __future__ import annotations

import json
import re
from collections import deque
from typing import Any, Iterator
from urllib.parse import parse_qs, urlparse, urlunparse

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
_LD_PRICE_TEXT_RE = re.compile(r"([0-9][0-9\s]{4,})\s*(?:\u0441\u0443\u043c|sum|so(?:['\u2019]|&#x27;|&#39;)?m)", re.I)
_PLAYWRIGHT_HANDLER = "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler"
_SITEMAP_LOC_RE = re.compile(r"<loc>\s*(https?://[^<\s]+)\s*</loc>", re.I)
_TECH_CATEGORY_HINTS = (
    "smartfon",
    "telefon",
    "phone",
    "noutbuk",
    "laptop",
    "planshet",
    "tablet",
    "televizor",
    "tv",
    "monitor",
    "gaming",
)
_LOW_VALUE_CATEGORY_HINTS = (
    "aksessuary-dlya-telefonov",
    "knopochnye-telefony",
)
_SITEMAP_PRODUCT_BATCH_SIZE = 160
_TEXNOMART_LISTING_SNAPSHOT_JS = """
(() => {
  const collect = (selector, limit) =>
    Array.from(document.querySelectorAll(selector))
      .map((el) => el.href)
      .filter(Boolean)
      .slice(0, limit);

  const productHrefs = collect('a[href*="/product/"]', 220);
  const categoryHrefs = collect('a[href*="/katalog/"], a[href*="/catalog/"]', 120);
  let host = document.getElementById("__scrapy_snapshot__");
  if (!host) {
    host = document.createElement("div");
    host.id = "__scrapy_snapshot__";
    host.style.display = "none";
    document.body.appendChild(host);
  }
  host.innerHTML =
    productHrefs.map((href) => `<a href="${href}">product</a>`).join("") +
    categoryHrefs.map((href) => `<a href="${href}">category</a>`).join("");
})();
"""


class TexnomartSpider(BaseProductSpider):
    _LISTING_PATH_RE = re.compile(r"^/(?:ru/)?katalog/[a-z0-9%+\-_/]+$", re.I)

    """Texnomart spider: listing -> PDP with lightweight extraction."""

    name = "texnomart"
    store_name = "texnomart"
    allowed_domains = ["texnomart.uz", "www.texnomart.uz"]
    product_sitemap_url = "https://texnomart.uz/sitemap.xml"
    category_url_map = {
        "phone": ("https://texnomart.uz/ru/katalog/smartfony/",),
        "laptop": ("https://texnomart.uz/ru/katalog/noutbuki/",),
        "tablet": ("https://texnomart.uz/ru/katalog/planshety/",),
        "tv": ("https://texnomart.uz/ru/katalog/televizory/",),
    }

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
        return self.target_start_category_urls((
            "https://texnomart.uz/ru/katalog/smartfony/",
            "https://texnomart.uz/ru/katalog/noutbuki/",
            "https://texnomart.uz/ru/katalog/planshety/",
            "https://texnomart.uz/ru/katalog/televizory/",
        ))

    def start_requests(self):
        discovery_mode = self._discovery_mode()
        if discovery_mode in {"sitemap", "hybrid"}:
            self.crawl_registry.categories_started_total += 1
            self._crawl_event(
                "CATEGORY_START",
                category_url=self.product_sitemap_url,
                page=1,
                discovery_mode=discovery_mode,
            )
            req = self.schedule_safe_request(
                self.product_sitemap_url,
                callback=self.parse_product_sitemap,
                purpose="listing",
                meta={
                    "category_url": self.product_sitemap_url,
                    "page": 1,
                    "empty_streak": 0,
                    "dup_sig_streak": 0,
                    "sitemap_product_offset": 0,
                },
            )
            if req is not None:
                yield req
            if discovery_mode == "sitemap":
                return
        yield from super().start_requests()

    def schedule_safe_request(
        self,
        url: str,
        *,
        callback,
        meta: dict[str, Any] | None = None,
        purpose: str = "listing",
        priority: int = 0,
    ):
        is_listing = purpose == "listing" or bool(self._LISTING_PATH_RE.match(urlparse(url).path.rstrip("/")))
        req_meta = dict(meta or {})
        req = super().schedule_safe_request(
            url, callback=callback, meta=req_meta, purpose=purpose, priority=priority
        )
        if req is None or not req.meta.get("playwright"):
            return req
        try:
            from scrapy_playwright.page import PageMethod
        except Exception:
            return req

        m = dict(req.meta)
        m.setdefault("playwright_include_page", False)
        m.setdefault("playwright_context", "default")
        if is_listing:
            m["playwright_page_methods"] = [
                PageMethod("wait_for_load_state", "domcontentloaded"),
                PageMethod("wait_for_timeout", 2200),
                PageMethod("evaluate", "window.scrollTo(0, Math.min(document.body.scrollHeight, 2200))"),
                PageMethod("wait_for_timeout", 1400),
                PageMethod("evaluate", "window.scrollTo(0, document.body.scrollHeight)"),
                PageMethod("wait_for_timeout", 1800),
                PageMethod("evaluate", _TEXNOMART_LISTING_SNAPSHOT_JS),
            ]
        else:
            m["playwright_page_methods"] = [
                PageMethod("wait_for_load_state", "domcontentloaded"),
                PageMethod("wait_for_timeout", 900),
            ]
        m["playwright_page_goto_kwargs"] = {"wait_until": "commit", "timeout": 90_000}
        return req.replace(meta=m)

    def parse_product_sitemap(self, response: scrapy.http.Response):
        from infrastructure.access.resource_governance import release_request_governance_counters

        release_request_governance_counters(dict(response.meta or {}), self.store_name or self.name)
        reg = self.crawl_registry
        category_url = str(response.meta.get("category_url") or response.url)
        product_urls = list(self._iter_product_urls_from_sitemap(response.text))

        if not getattr(self, "_texnomart_sitemap_seeded", False):
            self._texnomart_sitemap_seeded = True
            self._texnomart_sitemap_queue_drained_logged = False
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
                discovery_mode="sitemap",
            )
            self._seed_sitemap_product_queue(
                product_urls,
                category_url=category_url,
                from_listing=response.url,
            )

        yield from self._drain_pending_sitemap_products()

    def schedule_product_request(
        self,
        url: str,
        *,
        response: scrapy.http.Response,
        meta: dict[str, Any],
    ) -> scrapy.http.Request | None:
        clean_meta = dict(meta)
        for key in (
            "force_browser",
            "force_proxy",
            "playwright",
            "playwright_include_page",
            "playwright_context",
            "playwright_page_methods",
            "playwright_page_goto_kwargs",
            "playwright_page_init_callback",
            "prior_failures",
            "access_last_signal",
            "access_mode_selected",
        ):
            clean_meta.pop(key, None)
        abs_url = response.urljoin(url.strip())
        canon = self.canonicalize_product_url(abs_url)
        pm = {
            **clean_meta,
            "from_listing": response.url,
        }
        return self.schedule_safe_request(
            canon,
            callback=self.parse,
            purpose="product",
            meta=pm,
            priority=20,
        )

    def parse_product(self, response: scrapy.http.Response):
        yield from super().parse_product(response)
        yield from self._drain_pending_sitemap_products()

    def errback_default(self, failure):
        super().errback_default(failure)
        yield from self._drain_pending_sitemap_products()

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
            if any(slug in path_lower for slug in _LOW_VALUE_CATEGORY_HINTS):
                continue
            if not any(slug in path_lower for slug in _TECH_CATEGORY_HINTS):
                continue
            seen.add(path)
            out.append(path)
        return sorted(out)

    def extract_next_page_url(self, response: scrapy.http.Response) -> str | None:
        return self.extract_common_next_page_url(
            response,
            path_markers=("/catalog/", "/katalog/"),
        )

    @staticmethod
    def _extract_sitemap_locs(xml_text: str) -> list[str]:
        return [match.strip() for match in _SITEMAP_LOC_RE.findall(xml_text) if match.strip()]

    def _iter_product_urls_from_sitemap(self, xml_text: str) -> Iterator[str]:
        seen_urls: set[str] = set()
        seen_source_ids: set[str] = set()
        for url in self._extract_sitemap_locs(xml_text):
            parsed = urlparse(url)
            if "texnomart.uz" not in parsed.netloc.lower():
                continue
            if not _PRODUCT_PATH_RE.search(parsed.path):
                continue
            canonical = self.canonicalize_product_url(url)
            source_id = self.extract_source_id_from_url(canonical)
            if canonical in seen_urls:
                continue
            if source_id and source_id in seen_source_ids:
                continue
            seen_urls.add(canonical)
            if source_id:
                seen_source_ids.add(source_id)
            yield canonical

    def _build_internal_sitemap_request(
        self,
        url: str,
        *,
        meta: dict[str, Any],
    ) -> scrapy.http.Request | None:
        req = self.schedule_safe_request(
            url,
            callback=self.parse_product_sitemap,
            purpose="listing",
            meta=meta,
            priority=30,
        )
        if req is None:
            return None
        return req.replace(dont_filter=True)

    def _pending_sitemap_product_queue(self):
        queue = getattr(self, "_texnomart_pending_sitemap_products", None)
        if not isinstance(queue, deque):
            queue = deque()
            self._texnomart_pending_sitemap_products = queue
        seen = getattr(self, "_texnomart_pending_sitemap_product_urls", None)
        if not isinstance(seen, set):
            seen = set()
            self._texnomart_pending_sitemap_product_urls = seen
        return queue, seen

    def _seed_sitemap_product_queue(
        self,
        product_urls: list[str],
        *,
        category_url: str,
        from_listing: str,
    ) -> None:
        queue, seen = self._pending_sitemap_product_queue()
        if queue:
            return
        reg = self.crawl_registry
        page_seen_urls: set[str] = set()
        page_seen_source_ids: set[str] = set()
        base_meta = {
            "category_url": category_url,
            "from_listing": from_listing,
            "discovery_mode": "sitemap",
        }
        queued = 0
        for product_url in product_urls:
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
                continue
            if canonical_url in seen:
                continue
            queue.append((canonical_url, dict(base_meta)))
            seen.add(canonical_url)
            page_seen_urls.add(canonical_url)
            if source_id:
                page_seen_source_ids.add(source_id)
            queued += 1
        self._crawl_event(
            "SITEMAP_QUEUE_SEEDED",
            category_url=category_url,
            page=1,
            queued_count=queued,
        )

    def _schedule_sitemap_product_request(
        self,
        canonical_url: str,
        *,
        meta: dict[str, Any],
    ) -> scrapy.http.Request | None:
        clean_meta = dict(meta)
        for key in (
            "force_browser",
            "force_proxy",
            "playwright",
            "playwright_include_page",
            "playwright_context",
            "playwright_page_methods",
            "playwright_page_goto_kwargs",
            "playwright_page_init_callback",
            "prior_failures",
            "access_last_signal",
            "access_mode_selected",
        ):
            clean_meta.pop(key, None)
        clean_meta.setdefault("category_url", self.product_sitemap_url)
        clean_meta.setdefault("from_listing", self.product_sitemap_url)
        clean_meta.setdefault("discovery_mode", "sitemap")
        return self.schedule_safe_request(
            canonical_url,
            callback=self.parse,
            purpose="product",
            meta=clean_meta,
            priority=20,
        )

    def _drain_pending_sitemap_products(self):
        queue, seen = self._pending_sitemap_product_queue()
        drained = 0
        while queue and drained < _SITEMAP_PRODUCT_BATCH_SIZE:
            canonical_url, base_meta = queue[0]
            source_id = self.extract_source_id_from_url(canonical_url)
            if self.should_skip_product_url(canonical_url):
                queue.popleft()
                seen.discard(canonical_url)
                continue
            req = self._schedule_sitemap_product_request(
                canonical_url,
                meta=dict(base_meta),
            )
            if req is None:
                self._crawl_event(
                    "PRODUCT_DEFERRED",
                    category_url=str(base_meta.get("category_url") or self.product_sitemap_url),
                    page=1,
                    canonical_url=canonical_url,
                    reason="resource_governance",
                )
                break
            queue.popleft()
            seen.discard(canonical_url)
            self.crawl_registry.remember_product_url(canonical_url)
            if source_id:
                self.crawl_registry.remember_source_id(source_id)
            drained += 1
            yield req

        if queue or getattr(self, "_texnomart_sitemap_queue_drained_logged", False):
            return
        self._texnomart_sitemap_queue_drained_logged = True
        self._crawl_event(
            "PAGINATION_STOP",
            category_url=self.product_sitemap_url,
            page=1,
            reason="sitemap_queue_drained",
        )

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

    def canonicalize_product_url(self, url: str) -> str:
        canonical = super().canonicalize_product_url(url)
        parsed = urlparse(canonical)
        path = parsed.path or ""
        if _PRODUCT_PATH_RE.search(path) and not path.endswith("/"):
            path = f"{path}/"
        return urlunparse((parsed.scheme, parsed.netloc, path, "", parsed.query, parsed.fragment))

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
        for data in self._iter_ld_json_payloads(response):
            found = self._pick_product_node(data)
            if found is not None:
                return found
        return None

    def _iter_ld_json_payloads(self, response: scrapy.http.Response) -> Iterator[Any]:
        for raw in response.css('script[type="application/ld+json"]::text').getall():
            payload = (raw or "").strip()
            if not payload:
                continue
            try:
                yield json.loads(payload)
            except json.JSONDecodeError:
                continue

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
        ld_fallback = self._extract_ld_price_fallback(response, product_ld)
        if ld_fallback:
            return f"{ld_fallback} сум"

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

    def _extract_ld_price_fallback(
        self,
        response: scrapy.http.Response,
        product_ld: dict[str, Any] | None,
    ) -> str | None:
        text_candidates: list[str] = []
        ld_description = str((product_ld or {}).get("description") or "").strip()
        if ld_description:
            text_candidates.append(ld_description)
        meta_description = str(response.css('meta[name="description"]::attr(content)').get() or "").strip()
        if meta_description:
            text_candidates.append(meta_description)
        text_candidates.extend(self._iter_faq_ld_answer_texts(response))

        for candidate in text_candidates:
            match = _LD_PRICE_TEXT_RE.search(candidate)
            if not match:
                continue
            digits = self._digits_from_price_text(match.group(1))
            if digits:
                return digits
        return None

    def _iter_faq_ld_answer_texts(self, response: scrapy.http.Response) -> Iterator[str]:
        for data in self._iter_ld_json_payloads(response):
            nodes: list[Any]
            if isinstance(data, list):
                nodes = data
            else:
                nodes = [data]
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                if str(node.get("@type", "")).lower() != "faqpage":
                    continue
                for entry in node.get("mainEntity") or []:
                    if not isinstance(entry, dict):
                        continue
                    answer = entry.get("acceptedAnswer") or {}
                    if not isinstance(answer, dict):
                        continue
                    text = str(answer.get("text") or "").strip()
                    if text:
                        yield text

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

    def _discovery_mode(self) -> str:
        if self.has_crawl_targeting():
            return "categories"
        raw = str(getattr(self, "discovery_mode", "sitemap") or "sitemap").strip().lower()
        if raw in {"sitemap", "categories", "hybrid"}:
            return raw
        return "sitemap"
