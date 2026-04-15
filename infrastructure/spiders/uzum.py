from __future__ import annotations

from collections import deque
import hashlib
import json
import re
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import scrapy.http

from infrastructure.spiders.base import BaseProductSpider
from infrastructure.spiders.product_classifier import (
    classify_category,
    extract_brand,
    is_electronics_category_url,
)

_PLAYWRIGHT_HANDLER = "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler"
_UZUM_PRODUCT_PATH_RE = re.compile(r"^/(?:ru/)?product/[^/?#]+/?$", re.I)
_UZUM_ID_IN_PATH_RE = re.compile(r"-([0-9]{5,})(?:$|[/?#])")
_UZUM_SKU_RE = re.compile(r"(?:skuId|skuid)=([0-9]+)", re.I)
_UZUM_PRICE_NUM_RE = re.compile(r"(\d[\d\s\u00a0]{3,})")
_UZUM_MONEY_INLINE_RE = re.compile(
    r"(\d[\d\s\u00a0]{2,})\s*(?:сум|so['\u2019]?m|soum|uzs|лв)",
    re.I,
)
_UZUM_SUM_TEXT_RE = re.compile(
    r"[^<]{0,48}\d[\d\s\u00a0]{3,}[^<]{0,24}(?:сум|so['\u2019]?m|soum)",
    re.I,
)
_UZUM_PRODUCT_HREF_TEXT_RE = re.compile(r'["\'](/(?:ru/)?product/[^"\']+)["\']', re.I)
_UZUM_PRODUCT_ESCAPED_HREF_TEXT_RE = re.compile(r"\\/(?:ru\\/)?product\\/[^\"'\\s]+", re.I)
_UZUM_HOME_URL = "https://uzum.uz/ru"
_UZUM_PRIMARY_SMARTPHONE_CATEGORY_URL = "https://uzum.uz/ru/category/smartfony-12690"
_UZUM_LAPTOP_CATEGORY_URL = "https://uzum.uz/ru/category/noutbuki-15718"
_UZUM_TABLET_CATEGORY_URL = "https://uzum.uz/ru/category/planshety-i-elektronnye-knigi-15716"
_UZUM_TV_CATEGORY_URL = "https://uzum.uz/ru/category/televizory-12601"
_UZUM_BROWSER_GRAPH_EXPANSION_LIMIT = 8
_UZUM_PENDING_PRODUCT_DRAIN_LIMIT = 6
_UZUM_PENDING_GRAPH_DRAIN_LIMIT = 2
_UZUM_PRODUCT_GRAPH_FANOUT_LIMIT = 48
_UZUM_PHONE_CATEGORY_HINTS = (
    "smartfon",
    "iphone",
    "samsung",
    "xiaomi",
    "redmi",
    "poco",
    "honor",
    "oppo",
    "vivo",
    "realme",
    "tecno",
    "infinix",
    "huawei",
    "nothing",
    "oneplus",
)
_UZUM_TECH_CATEGORY_HINTS = _UZUM_PHONE_CATEGORY_HINTS + (
    "noutbuk",
    "macbook",
    "laptop",
    "planshet",
    "tablet",
    "ipad",
    "televizor",
    "smart-tv",
    "tv",
    "umnye-chasy",
    "smart-chasy",
)
_UZUM_LOW_VALUE_CATEGORY_HINTS = (
    "smartfony-i-telefony",
    "knopochnye-telefony",
    "radiotelefony",
    "stacionarnye-telefony",
    "provodnye-telefony",
    "smartfony-android",
    "smartfony-apple-iphoneios",
    "smartfony-na-drugikh-os",
    "vosstanovlennye-smartfony",
    "aksessuary",
    "aksessuary-i-zapchasti",
    "zapchasti-i-remont",
    "aksessuary-dlya-noutbukov",
    "kabeli-i-perekhodniki",
    "oborudovanie-dlya-televizorov",
    "aksessuary-dlya-prosmotra",
    "kompyuternaya-tekhnika",
    "kompyuternaya-periferiya",
    "periferiya-i-aksessuary",
    "komplektuyuschie-dlya-kompyuternoj-tekhniki",
    "naushniki-i-audiotekhnika",
    "audiotekhnika",
    "noutbuki-planshety-i-elektronnye",
    "televizory-i-videotekhnika",
)
_UZUM_LISTING_SNAPSHOT_JS = """
(() => {
  const collect = (selector, limit) =>
    Array.from(document.querySelectorAll(selector))
      .map((el) => el.href)
      .filter(Boolean)
      .slice(0, limit);

  const productHrefs = collect('a[href*="/product/"]', 160);
  const categoryHrefs = collect('a[href*="/category/"]', 80);
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
_UZUM_PRODUCT_GRAPH_LINKS_JS = """
(() => Array.from(
  new Set(
    Array.from(document.querySelectorAll('a[href*="/product/"]'))
      .map((el) => el.href)
      .filter(Boolean)
  )
).slice(0, 160))();
"""

class UzumSpider(BaseProductSpider):
    """UZUM marketplace spider with Playwright-backed listing/PDP parsing."""

    name = "uzum"
    store_name = "uzum"
    allowed_domains = ["uzum.uz"]

    custom_settings = {
        **BaseProductSpider.custom_settings,
        "DOWNLOAD_HANDLERS": {
            "https": _PLAYWRIGHT_HANDLER,
            "http": _PLAYWRIGHT_HANDLER,
        },
        "PLAYWRIGHT_BROWSER_TYPE": "chromium",
        "PLAYWRIGHT_LAUNCH_OPTIONS": {"headless": True},
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 90_000,
        "PLAYWRIGHT_MAX_PAGES_PER_CONTEXT": 2,
        "PLAYWRIGHT_CONTEXTS": {
            "default": {
                "locale": "ru-RU",
                "timezone_id": "Asia/Tashkent",
                "viewport": {"width": 1440, "height": 2200},
                "user_agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                ),
            }
        },
        # Conservative browser parallelism reduces flaky DNS/timeouts on heavy pages.
        "CONCURRENT_REQUESTS": 8,
        "RETRY_TIMES": 4,
        "DOWNLOAD_TIMEOUT": 90,
        "DOWNLOAD_DELAY": 1.0,
    }

    def start_category_urls(self) -> tuple[str, ...]:
        return (
            _UZUM_PRIMARY_SMARTPHONE_CATEGORY_URL,
            _UZUM_LAPTOP_CATEGORY_URL,
            _UZUM_TABLET_CATEGORY_URL,
            _UZUM_TV_CATEGORY_URL,
        )

    def start_requests(self):
        discovery_mode = self._discovery_mode()
        if discovery_mode in {"homepage", "hybrid"}:
            self.crawl_registry.categories_started_total += 1
            self._crawl_event(
                "CATEGORY_START",
                category_url=_UZUM_HOME_URL,
                page=1,
                discovery_mode=discovery_mode,
            )
            req = self.schedule_safe_request(
                _UZUM_HOME_URL,
                callback=self.parse_homepage_seed,
                purpose="listing",
                meta={
                    "category_url": _UZUM_HOME_URL,
                    "page": 1,
                    "empty_streak": 0,
                    "dup_sig_streak": 0,
                    "discovery_mode": discovery_mode,
                    "playwright_include_page": True,
                    "seed_kind": "homepage",
                },
            )
            if req is not None:
                yield req
            if discovery_mode == "homepage":
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
        is_listing = purpose == "listing" or "/category/" in url
        req_meta = dict(meta or {})
        if is_listing:
            # Uzum still needs Playwright to hydrate listing cards reliably.
            req_meta.setdefault("force_browser", True)
        req = super().schedule_safe_request(
            url, callback=callback, meta=req_meta, purpose=purpose, priority=priority
        )
        if req is None:
            return None
        if not req.meta.get("playwright"):
            return req
        try:
            from scrapy_playwright.page import PageMethod
        except Exception:
            return req

        m = dict(req.meta)
        m.setdefault("playwright_include_page", False)
        m.setdefault("playwright_context", "default")
        if is_listing:
            # Scroll through the hydrated listing, then mirror the live anchors into
            # the DOM snapshot so Scrapy sees real PDP/category hrefs in response.text.
            m["playwright_page_methods"] = [
                PageMethod("wait_for_load_state", "domcontentloaded"),
                PageMethod("wait_for_timeout", 4000),
                PageMethod("evaluate", "window.scrollTo(0, Math.min(document.body.scrollHeight, 2500))"),
                PageMethod("wait_for_timeout", 1800),
                PageMethod("evaluate", "window.scrollTo(0, Math.min(document.body.scrollHeight, 5000))"),
                PageMethod("wait_for_timeout", 1800),
                PageMethod("evaluate", "window.scrollTo(0, document.body.scrollHeight)"),
                PageMethod("wait_for_timeout", 3000),
                PageMethod("evaluate", "window.scrollTo(0, document.body.scrollHeight)"),
                PageMethod("wait_for_timeout", 3000),
                PageMethod("evaluate", _UZUM_LISTING_SNAPSHOT_JS),
            ]
        else:
            m["playwright_page_methods"] = [
                PageMethod("wait_for_load_state", "domcontentloaded"),
                PageMethod("wait_for_timeout", 1200),
            ]
        m["playwright_page_goto_kwargs"] = {"wait_until": "commit", "timeout": 90_000}
        return req.replace(meta=m)

    def request_meta_extra(self) -> dict[str, Any]:
        # Listing requests opt into browser mode in ``schedule_safe_request``.
        # PDP requests stay plain HTTP by default because live Uzum product pages
        # already expose the full ProductGroup JSON-LD without browser rendering.
        return {}

    async def parse_homepage_seed(self, response: scrapy.http.Response):
        # Homepage seeding bypasses BaseProductSpider.parse(), so we must release
        # the browser governance counters here to avoid leaking one permanent
        # browser slot for the rest of the crawl.
        from infrastructure.access.resource_governance import release_request_governance_counters

        release_request_governance_counters(dict(response.meta or {}), self.store_name or self.name)
        page = response.meta.get("playwright_page")
        if page is None:
            return list(self.parse_listing(response))

        hrefs: list[str] = []
        try:
            await page.wait_for_timeout(4000)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(3000)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(3000)
            hrefs = await page.eval_on_selector_all(
                'a[href*="/product/"]',
                "els => Array.from(new Set(els.map(e => e.href).filter(Boolean))).slice(0, 160)",
            )
        finally:
            await page.close()

        if not hrefs:
            return list(self.parse_listing(response))

        reg = self.crawl_registry
        category_url = str(response.meta.get("category_url") or response.url)
        page_num = int(response.meta.get("page") or 1)
        reg.note_pagination_depth(page_num)
        reg.remember_listing_page_url(response.url)
        reg.listing_pages_seen_total += 1
        reg.listing_cards_seen_total += len(hrefs)
        reg.record_category_with_results(category_url)
        self.log_empty_listing_page(
            response,
            category_url=category_url,
            page=page_num,
            extracted_count=len(hrefs),
        )
        reg.record_listing_stats(listing_url=response.url, product_urls_found=len(hrefs))

        from infrastructure.observability import message_codes as obs_mc
        from infrastructure.observability.event_logger import log_sync_event

        log_sync_event(
            "crawl",
            "info",
            obs_mc.CRAWL_LISTING_SEEN,
            self._obs_corr_crawl(category_url=category_url, source_url=response.url),
            metrics={"page": page_num, "product_links": len(hrefs)},
        )

        outputs = list(self._schedule_product_requests_from_candidates(response, hrefs))
        self._crawl_event(
            "PAGINATION_STOP",
            category_url=category_url,
            page=page_num,
            reason="no_next_url",
            empty_streak=0,
            dup_sig_streak=0,
        )
        return outputs

    def is_product_page(self, response: scrapy.http.Response) -> bool:
        return bool(_UZUM_PRODUCT_PATH_RE.search(urlparse(response.url).path))

    def extract_listing_product_urls(self, response: scrapy.http.Response) -> list[str]:
        candidates: list[str] = []
        for href in response.css('a[href*="/product/"]::attr(href)').getall():
            if not href:
                continue
            full = response.urljoin(href.strip())
            parsed = urlparse(full)
            if "uzum.uz" not in parsed.netloc:
                continue
            if not _UZUM_PRODUCT_PATH_RE.search(parsed.path):
                continue
            candidates.append(full)
        # Fallback: parse any serialized href occurrences in raw HTML.
        if not candidates:
            for href in _UZUM_PRODUCT_HREF_TEXT_RE.findall(response.text):
                full = response.urljoin(href.strip())
                parsed = urlparse(full)
                if "uzum.uz" in parsed.netloc and _UZUM_PRODUCT_PATH_RE.search(parsed.path):
                    candidates.append(full)
        if not candidates:
            for href in _UZUM_PRODUCT_ESCAPED_HREF_TEXT_RE.findall(response.text):
                full = response.urljoin(href.replace("\\/", "/").strip())
                parsed = urlparse(full)
                if "uzum.uz" in parsed.netloc and _UZUM_PRODUCT_PATH_RE.search(parsed.path):
                    candidates.append(full)
        # Product URLs are often repeated in carousels; keep deterministic unique order.
        seen: set[str] = set()
        out: list[str] = []
        for u in candidates:
            if u in seen:
                continue
            seen.add(u)
            out.append(u)
        return out

    def extract_listing_category_urls(self, response: scrapy.http.Response) -> list[str]:
        if "/category/" not in urlparse(response.url).path:
            return []
        candidates: list[str] = []
        for href in response.css('a[href*="/category/"]::attr(href), a[href*="/catalog/"]::attr(href)').getall():
            if not href:
                continue
            full = response.urljoin(href.strip())
            parsed = urlparse(full)
            if "uzum.uz" not in parsed.netloc:
                continue
            path = parsed.path.rstrip("/")
            if _UZUM_PRODUCT_PATH_RE.search(path):
                continue
            # Gate on electronics/appliance category allowlist to avoid food, clothing etc.
            if not is_electronics_category_url(full):
                continue
            candidates.append(full)

        if not candidates:
            for href in re.findall(r'["\'](/(?:ru/)?(?:category|catalog)/[^"\']+)["\']', response.text, re.I):
                full = response.urljoin(href.strip())
                parsed = urlparse(full)
                path = parsed.path.rstrip("/")
                if (
                    "uzum.uz" in parsed.netloc
                    and not _UZUM_PRODUCT_PATH_RE.search(path)
                    and is_electronics_category_url(full)
                ):
                    candidates.append(full)

        current = urlparse(response.url).path.rstrip("/")
        seen: set[str] = set()
        out: list[str] = []
        for url in candidates:
            path = urlparse(url).path.rstrip("/")
            if not path or path == current:
                continue
            if path in seen:
                continue
            path_lower = path.lower()
            if any(slug in path_lower for slug in _UZUM_LOW_VALUE_CATEGORY_HINTS):
                continue
            if not any(slug in path_lower for slug in _UZUM_TECH_CATEGORY_HINTS):
                continue
            seen.add(path)
            out.append(path)
        return sorted(out)

    def extract_next_page_url(self, response: scrapy.http.Response) -> str | None:
        # First, prefer explicit "next" links if they exist.
        next_href = (
            response.css('a[rel="next"]::attr(href)').get()
            or response.css('link[rel="next"]::attr(href)').get()
        )
        if next_href:
            return response.urljoin(next_href)
        # Fallback for catalog pages with page query parameter.
        # BaseProductSpider stop conditions prevent infinite loops on repeated pages.
        if not self.extract_listing_product_urls(response):
            return None
        parsed = urlparse(response.url)
        if "/category/" not in parsed.path:
            return None
        q = parse_qs(parsed.query)
        page = int(q.get("page", ["1"])[0] or "1")
        q["page"] = [str(page + 1)]
        new_query = urlencode({k: v[0] for k, v in q.items()})
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", new_query, ""))

    def build_listing_signature(
        self,
        response: scrapy.http.Response,
        canonical_product_urls: list[str],
        page: int,
    ) -> str:
        # Uzum frequently serves the same hydrated card set behind incrementing
        # ``page=`` URLs. Ignore the page number so repeated 48-card shells trip
        # the duplicate-listing guard instead of burning the whole bounded run.
        head = sorted(canonical_product_urls[:24])
        blob = {
            "path": urlparse(response.url).path.rstrip("/"),
            "head_urls": head,
            "total_links": len(canonical_product_urls),
        }
        return hashlib.sha256(
            json.dumps(blob, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def parse_product(self, response: scrapy.http.Response):
        yield from super().parse_product(response)
        graph_req = self._build_browser_graph_request(response)
        if graph_req is not None:
            yield graph_req
        yield from self._drain_pending_graph_candidates(response)
        # Reserve the just-freed slot for browser graph expansion first; otherwise
        # draining deferred plain PDPs can starve deeper discovery and cap runs early.
        yield from self._drain_pending_product_candidates(response)

    def extract_source_id_from_url(self, url: str) -> str | None:
        parsed = urlparse(url)
        sku = parse_qs(parsed.query).get("skuId")
        if sku and sku[0].strip():
            return f"sku:{sku[0].strip()}"
        path_match = _UZUM_ID_IN_PATH_RE.search(parsed.path + "/")
        if path_match:
            return f"p:{path_match.group(1)}"
        return None

    def full_parse_item(self, response: scrapy.http.Response) -> dict[str, Any] | None:
        if not self.is_product_page(response):
            return None
        product_ld = self._extract_product_ld(response)
        title = self._extract_title(response, product_ld)
        source_id = (
            self._source_id_from_ld(product_ld)
            or self.extract_source_id_from_url(response.url)
            or self._fallback_source_id(response.url)
        )
        if not title or not source_id:
            return None
        price_str = self._extract_price_str(response, product_ld)
        in_stock = self._extract_in_stock(response, product_ld)
        image_urls = self._extract_image_urls(response, product_ld)
        raw_specs = self._extract_raw_specs(product_ld)
        raw_specs.update(self._extract_raw_specs_html(response))
        return {
            "url": response.url,
            "title": title,
            "name": title,
            "source_id": source_id,
            "external_id": source_id,
            "source": self.store_name,
            "price_str": price_str,
            "in_stock": in_stock,
            "brand": self._extract_brand(title, product_ld),
            "description": self._extract_description(product_ld),
            "raw_specs": raw_specs,
            "image_urls": image_urls,
            "category_hint": self.extract_category_hint(response, title),
        }

    def schedule_product_request(
        self,
        url: str,
        *,
        response: scrapy.http.Response,
        meta: dict[str, Any],
    ) -> scrapy.http.Request | None:
        # Product pages inherit listing meta in ``BaseProductSpider``. On Uzum that
        # would wrongly carry ``force_browser=True`` from category pages and collapse
        # product throughput back to Playwright-only mode. Keep browser on listings,
        # but reset PDP requests to plain-first.
        clean_meta = dict(meta)
        for key in (
            "force_browser",
            "playwright",
            "playwright_include_page",
            "playwright_context",
            "playwright_page_methods",
            "playwright_page_goto_kwargs",
            "playwright_page_init_callback",
        ):
            clean_meta.pop(key, None)
        abs_url = response.urljoin(url.strip())
        canon = self.canonicalize_product_url(abs_url)
        pm = {
            **clean_meta,
            "from_listing": response.url,
        }
        req = self.schedule_safe_request(
            canon,
            callback=self.parse,
            purpose="product",
            meta=pm,
            priority=20,
        )
        if req is None:
            return None
        return req.replace(dont_filter=True)

    def extract_category_hint(
        self,
        response_or_url: scrapy.http.Response | str,
        title: str | None = None,
    ) -> str | None:
        url = response_or_url.url if hasattr(response_or_url, "url") else str(response_or_url)
        return classify_category(url, title or "")

    def _extract_product_ld(self, response: scrapy.http.Response) -> dict[str, Any] | None:
        expected_source_id = self.extract_source_id_from_url(response.url) or self._fallback_source_id(response.url)
        blocks = response.css('script[type="application/ld+json"]::text').getall()
        for raw in blocks:
            payload = (raw or "").strip()
            if not payload:
                continue
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                continue
            found = self._pick_product_node(
                data,
                expected_source_id=expected_source_id,
                response_url=response.url,
            )
            if found is not None:
                return found
        return None

    def _pick_product_node(
        self,
        data: Any,
        *,
        expected_source_id: str | None = None,
        response_url: str | None = None,
    ) -> dict[str, Any] | None:
        def _is_type(v: Any, expected: str) -> bool:
            if isinstance(v, str):
                return v.lower() == expected
            if isinstance(v, list):
                return any(isinstance(x, str) and x.lower() == expected for x in v)
            return False

        def _scan_nodes(nodes: list[Any]) -> dict[str, Any] | None:
            for node in nodes:
                if isinstance(node, dict) and _is_type(node.get("@type"), "productgroup"):
                    merged = self._merge_product_group(
                        node,
                        expected_source_id=expected_source_id,
                        response_url=response_url,
                    )
                    if merged is not None:
                        return merged
            preferred: list[dict[str, Any]] = []
            fallback: list[dict[str, Any]] = []
            for node in nodes:
                if not isinstance(node, dict) or not _is_type(node.get("@type"), "product"):
                    continue
                if self._ld_node_matches_page(
                    node,
                    expected_source_id=expected_source_id,
                    response_url=response_url,
                ):
                    preferred.append(node)
                else:
                    fallback.append(node)
            if preferred:
                return preferred[0]
            if fallback:
                return fallback[0]
            return None

        if isinstance(data, dict):
            if _is_type(data.get("@type"), "productgroup"):
                merged = self._merge_product_group(
                    data,
                    expected_source_id=expected_source_id,
                    response_url=response_url,
                )
                if merged is not None:
                    return merged
            if _is_type(data.get("@type"), "product"):
                return data
            graph = data.get("@graph")
            if isinstance(graph, list):
                found = _scan_nodes(graph)
                if found is not None:
                    return found
        if isinstance(data, list):
            found = _scan_nodes(data)
            if found is not None:
                return found
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

    def _extract_price_str(self, response: scrapy.http.Response, product_ld: dict[str, Any] | None) -> str:
        offers = (product_ld or {}).get("offers")
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        if isinstance(offers, dict):
            price = offers.get("price")
            if price not in (None, ""):
                return f"{str(price).strip()} сум"
        for sel in (
            'meta[property="product:price:amount"]::attr(content)',
            'meta[property="og:price:amount"]::attr(content)',
            '[itemprop="price"]::attr(content)',
        ):
            raw = response.css(sel).get()
            if raw and str(raw).strip():
                return f"{str(raw).strip()} сум"
        for txt in response.css("*::text").getall():
            cleaned = re.sub(r"\s+", " ", (txt or "")).strip()
            low = cleaned.lower()
            if "сум" not in low and "soum" not in low and "so'm" not in low and "uzs" not in low:
                continue
            m = _UZUM_MONEY_INLINE_RE.search(cleaned) or _UZUM_PRICE_NUM_RE.search(cleaned)
            if m:
                return f"{m.group(1).strip()} сум"
        frag = _UZUM_SUM_TEXT_RE.search(response.text)
        if frag:
            cleaned = re.sub(r"\s+", " ", frag.group(0)).strip()
            m = _UZUM_MONEY_INLINE_RE.search(cleaned) or _UZUM_PRICE_NUM_RE.search(cleaned)
            if m:
                return f"{m.group(1).strip()} сум"
        return ""

    def _extract_in_stock(self, response: scrapy.http.Response, product_ld: dict[str, Any] | None) -> bool:
        offers = (product_ld or {}).get("offers")
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        if isinstance(offers, dict):
            av = str(offers.get("availability") or "").lower()
            if av:
                return "outofstock" not in av and "discontinued" not in av
        text = response.text.lower()
        return "нет в наличии" not in text and "out of stock" not in text

    def _extract_image_urls(self, response: scrapy.http.Response, product_ld: dict[str, Any] | None) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()

        def add(val: str) -> None:
            u = response.urljoin((val or "").strip())
            if not u or u in seen or u.startswith("data:"):
                return
            if u.endswith((".svg", ".ico")):
                return
            seen.add(u)
            out.append(u)

        raw_img = (product_ld or {}).get("image")
        if isinstance(raw_img, str):
            add(raw_img)
        elif isinstance(raw_img, list):
            for x in raw_img:
                if isinstance(x, str):
                    add(x)
                elif isinstance(x, dict) and isinstance(x.get("url"), str):
                    add(str(x["url"]))
        for sel in (
            'meta[property="og:image"]::attr(content)',
            'meta[property="og:image:secure_url"]::attr(content)',
            'meta[name="twitter:image"]::attr(content)',
        ):
            v = response.css(sel).get()
            if v:
                add(v)
        for attr in ("src", "data-src", "srcset"):
            for v in response.css(f"img::attr({attr})").getall():
                if not v:
                    continue
                # srcset can include several candidates.
                part = v.split(",")[0].strip().split(" ")[0]
                add(part)
        return out

    def _extract_brand(self, title: str, product_ld: dict[str, Any] | None) -> str:
        raw = (product_ld or {}).get("brand")
        ld_brand: str | None = None
        if isinstance(raw, dict):
            ld_brand = str(raw.get("name") or "").strip() or None
        elif isinstance(raw, str):
            ld_brand = raw.strip() or None
        return extract_brand(title, ld_brand)

    def _extract_description(self, product_ld: dict[str, Any] | None) -> str:
        return re.sub(r"\s+", " ", str((product_ld or {}).get("description") or "")).strip()

    def _extract_raw_specs(self, product_ld: dict[str, Any] | None) -> dict[str, Any]:
        props = (product_ld or {}).get("additionalProperty")
        if not isinstance(props, list):
            return {}
        specs: dict[str, Any] = {}
        for entry in props:
            if not isinstance(entry, dict):
                continue
            key = re.sub(r"\s+", " ", str(entry.get("name") or "")).strip()
            val = re.sub(r"\s+", " ", str(entry.get("value") or "")).strip()
            if key and val and key not in specs:
                specs[key] = val
        return specs

    def _extract_raw_specs_html(self, response: scrapy.http.Response) -> dict[str, Any]:
        specs: dict[str, Any] = {}
        for prop in response.css('[itemprop="additionalProperty"]'):
            name = prop.css('[itemprop="name"]::text').get() or prop.css("::attr(name)").get()
            val = prop.css('[itemprop="value"]::text').get()
            if not val:
                val = " ".join(prop.css('[itemprop="value"] *::text').getall())
            k = re.sub(r"\s+", " ", str(name or "")).strip()
            v = re.sub(r"\s+", " ", str(val or "")).strip()
            if k and v and k not in specs:
                specs[k] = v
        for row in response.css("table tr"):
            cells = row.css("td, th")
            if len(cells) < 2:
                continue
            k = re.sub(r"\s+", " ", " ".join(cells[0].css("::text").getall()).strip())
            v = re.sub(r"\s+", " ", " ".join(cells[1].css("::text").getall()).strip())
            if k and v and len(k) < 200 and k not in specs:
                specs[k] = v
        return specs

    def _source_id_from_ld(self, product_ld: dict[str, Any] | None) -> str | None:
        sku = str((product_ld or {}).get("sku") or "").strip()
        if sku:
            return f"sku:{sku}"
        product_id = str((product_ld or {}).get("productID") or "").strip()
        if product_id:
            return product_id
        product_group_id = str((product_ld or {}).get("productGroupID") or "").strip()
        if product_group_id:
            return f"pg:{product_group_id}"
        return None

    def _fallback_source_id(self, url: str) -> str | None:
        sku_match = _UZUM_SKU_RE.search(url)
        if sku_match:
            return f"sku:{sku_match.group(1)}"
        path_match = _UZUM_ID_IN_PATH_RE.search(urlparse(url).path + "/")
        if path_match:
            return f"p:{path_match.group(1)}"
        return None

    def parse_product_graph_browser(self, response: scrapy.http.Response):
        # This callback bypasses BaseProductSpider.parse(), so we must release
        # resource-governance counters here to avoid leaking browser slots.
        from infrastructure.access.resource_governance import release_request_governance_counters

        release_request_governance_counters(dict(response.meta or {}), self.store_name or self.name)
        hrefs = self._extract_graph_browser_links(response)
        outputs = list(self._schedule_product_requests_from_candidates(response, hrefs))
        outputs.extend(list(self._drain_pending_graph_candidates(response)))
        outputs.extend(list(self._drain_pending_product_candidates(response)))
        return outputs

    def _build_browser_graph_request(
        self,
        response: scrapy.http.Response,
    ) -> scrapy.http.Request | None:
        if response.status != 200:
            return None
        depth = int(response.meta.get("graph_depth") or 0)
        canon = self.canonicalize_product_url(response.url)
        base_meta = self._graph_seed_meta_from_response(response)
        return self._schedule_graph_request_from_seed(
            canonical_url=canon,
            graph_seed_url=response.url,
            graph_depth=depth,
            base_meta=base_meta,
            enqueue_on_blocked=True,
        )

    def _graph_seed_meta_from_response(self, response: scrapy.http.Response) -> dict[str, Any]:
        base: dict[str, Any] = {}
        for key in ("category_url", "page", "discovery_mode", "from_listing", "seed_kind"):
            value = response.meta.get(key)
            if value is not None:
                base[key] = value
        return base

    def _pending_graph_queue(self):
        queue = getattr(self, "_uzum_pending_graph_candidates", None)
        if not isinstance(queue, deque):
            queue = deque()
            self._uzum_pending_graph_candidates = queue
        seen = getattr(self, "_uzum_pending_graph_candidate_urls", None)
        if not isinstance(seen, set):
            seen = set()
            self._uzum_pending_graph_candidate_urls = seen
        return queue, seen

    def _enqueue_pending_graph_seed(
        self,
        *,
        canonical_url: str,
        graph_seed_url: str,
        graph_depth: int,
        base_meta: dict[str, Any],
    ) -> None:
        queue, seen = self._pending_graph_queue()
        if canonical_url in seen:
            return
        queue.append((canonical_url, graph_seed_url, int(graph_depth), dict(base_meta)))
        seen.add(canonical_url)
        self._crawl_event("PRODUCT_GRAPH_DEFERRED", canonical_url=canonical_url, reason="resource_governance")

    def _drain_pending_graph_candidates(self, response: scrapy.http.Response):
        queue, seen = self._pending_graph_queue()
        drained = 0
        while queue and drained < _UZUM_PENDING_GRAPH_DRAIN_LIMIT:
            canonical_url, graph_seed_url, graph_depth, base_meta = queue[0]
            req = self._schedule_graph_request_from_seed(
                canonical_url=str(canonical_url),
                graph_seed_url=str(graph_seed_url),
                graph_depth=int(graph_depth),
                base_meta=dict(base_meta or {}),
                enqueue_on_blocked=False,
            )
            if req is None:
                break
            queue.popleft()
            seen.discard(str(canonical_url))
            drained += 1
            yield req

    def _schedule_graph_request_from_seed(
        self,
        *,
        canonical_url: str,
        graph_seed_url: str,
        graph_depth: int,
        base_meta: dict[str, Any],
        enqueue_on_blocked: bool,
    ) -> scrapy.http.Request | None:
        if graph_depth >= 1:
            return None

        started = int(getattr(self, "_uzum_browser_graph_expansions_started", 0) or 0)
        if started >= _UZUM_BROWSER_GRAPH_EXPANSION_LIMIT:
            return None

        expanded_urls = getattr(self, "_uzum_browser_graph_expanded_urls", None)
        if not isinstance(expanded_urls, set):
            expanded_urls = set()
            self._uzum_browser_graph_expanded_urls = expanded_urls
        if canonical_url in expanded_urls:
            return None

        req = self.schedule_safe_request(
            canonical_url,
            callback=self.parse_product_graph_browser,
            purpose="product",
            priority=5,
            meta={
                **dict(base_meta or {}),
                "force_browser": True,
                "playwright_include_page": True,
                "graph_depth": graph_depth + 1,
                "graph_seed_url": graph_seed_url,
            },
        )
        if req is None:
            if enqueue_on_blocked:
                self._enqueue_pending_graph_seed(
                    canonical_url=canonical_url,
                    graph_seed_url=graph_seed_url,
                    graph_depth=graph_depth,
                    base_meta=base_meta,
                )
            return None

        # Resource governance may silently downgrade browser intents to plain HTTP.
        # For graph expansion this is not useful, so rollback counters and retry
        # later through the deferred graph queue when a real browser slot frees up.
        mode = str(req.meta.get("access_mode_selected") or "").lower()
        if mode != "browser" or not bool(req.meta.get("playwright")):
            from infrastructure.access.resource_governance import release_request_governance_counters

            release_request_governance_counters(dict(req.meta or {}), self.store_name or self.name)
            if enqueue_on_blocked:
                self._enqueue_pending_graph_seed(
                    canonical_url=canonical_url,
                    graph_seed_url=graph_seed_url,
                    graph_depth=graph_depth,
                    base_meta=base_meta,
                )
            return None

        expanded_urls.add(canonical_url)
        self._uzum_browser_graph_expansions_started = started + 1
        try:
            from scrapy_playwright.page import PageMethod
        except Exception:
            return req.replace(dont_filter=True)

        graph_methods = [
            PageMethod("wait_for_load_state", "domcontentloaded"),
            PageMethod("wait_for_timeout", 3500),
            PageMethod("evaluate", "window.scrollTo(0, document.body.scrollHeight)"),
            PageMethod("wait_for_timeout", 2500),
            PageMethod("evaluate", "window.scrollTo(0, document.body.scrollHeight)"),
            PageMethod("wait_for_timeout", 2500),
            PageMethod("evaluate", _UZUM_PRODUCT_GRAPH_LINKS_JS),
        ]
        meta = dict(req.meta)
        meta["playwright_include_page"] = False
        meta["playwright_page_methods"] = graph_methods
        meta["uzum_graph_links_method_index"] = len(graph_methods) - 1
        return req.replace(meta=meta, dont_filter=True)

    def _schedule_product_requests_from_candidates(
        self,
        response: scrapy.http.Response,
        candidates: list[str],
    ):
        reg = self.crawl_registry
        page = int(response.meta.get("page") or 1)
        category_url = str(response.meta.get("category_url") or response.url)
        page_seen_urls: set[str] = set()
        page_seen_source_ids: set[str] = set()
        scheduled = 0

        for raw_url in candidates:
            raw_text = str(raw_url or "").strip()
            if not raw_text or "{" in raw_text or "}" in raw_text:
                continue
            abs_url = response.urljoin(raw_text)
            canon = self.canonicalize_product_url(abs_url)
            path = urlparse(canon).path
            if not _UZUM_PRODUCT_PATH_RE.search(path):
                continue
            sid = self.extract_source_id_from_url(canon)
            reg.product_urls_seen_total += 1

            if canon in page_seen_urls or (sid and sid in page_seen_source_ids):
                reg.product_urls_deduped_total += 1
                self._crawl_event(
                    "PRODUCT_DEDUPED",
                    category_url=category_url,
                    page=page,
                    canonical_url=canon,
                    reason="product_graph_page_duplicate",
                )
                continue

            if self.should_skip_product_url(canon):
                reg.product_urls_deduped_total += 1
                self._crawl_event(
                    "PRODUCT_DEDUPED",
                    category_url=category_url,
                    page=page,
                    canonical_url=canon,
                    reason="product_graph_seen",
                )
                continue

            req = self.schedule_product_request(
                abs_url,
                response=response,
                meta=dict(response.meta),
            )
            if req is None:
                self._enqueue_pending_product_candidate(abs_url, dict(response.meta))
                page_seen_urls.add(canon)
                if sid:
                    page_seen_source_ids.add(sid)
                self._crawl_event(
                    "PRODUCT_SCHEDULE_BLOCKED",
                    category_url=category_url,
                    page=page,
                    canonical_url=canon,
                    reason="product_graph_resource_or_policy_gate",
                )
                continue

            reg.remember_product_url(canon)
            page_seen_urls.add(canon)
            if sid:
                reg.remember_source_id(sid)
                page_seen_source_ids.add(sid)
            scheduled += 1
            yield req
            if scheduled >= _UZUM_PRODUCT_GRAPH_FANOUT_LIMIT:
                break

    def _extract_graph_browser_links(self, response: scrapy.http.Response) -> list[str]:
        methods = response.meta.get("playwright_page_methods") or []
        idx = response.meta.get("uzum_graph_links_method_index")
        if isinstance(idx, int) and 0 <= idx < len(methods):
            method = methods[idx]
            result = getattr(method, "result", None)
            if isinstance(result, list):
                return [str(item).strip() for item in result if str(item or "").strip()]
        return []

    def _pending_product_queue(self):
        queue = getattr(self, "_uzum_pending_product_candidates", None)
        if not isinstance(queue, deque):
            queue = deque()
            self._uzum_pending_product_candidates = queue
        seen = getattr(self, "_uzum_pending_product_candidate_urls", None)
        if not isinstance(seen, set):
            seen = set()
            self._uzum_pending_product_candidate_urls = seen
        return queue, seen

    def _enqueue_pending_product_candidate(self, abs_url: str, meta: dict[str, Any]) -> None:
        canon = self.canonicalize_product_url(abs_url)
        if self.should_skip_product_url(canon):
            return
        queue, seen = self._pending_product_queue()
        if canon in seen:
            return
        queue.append((abs_url, dict(meta)))
        seen.add(canon)
        self._crawl_event("PRODUCT_DEFERRED", canonical_url=canon, reason="resource_governance")

    def _drain_pending_product_candidates(self, response: scrapy.http.Response):
        queue, seen = self._pending_product_queue()
        drained = 0
        while queue and drained < _UZUM_PENDING_PRODUCT_DRAIN_LIMIT:
            abs_url, meta = queue[0]
            canon = self.canonicalize_product_url(abs_url)
            sid = self.extract_source_id_from_url(canon)
            if self.should_skip_product_url(canon):
                queue.popleft()
                seen.discard(canon)
                continue
            req = self.schedule_product_request(
                abs_url,
                response=response,
                meta=dict(meta),
            )
            if req is None:
                break
            queue.popleft()
            seen.discard(canon)
            self.crawl_registry.remember_product_url(canon)
            if sid:
                self.crawl_registry.remember_source_id(sid)
            drained += 1
            yield req

    def _merge_product_group(
        self,
        group: dict[str, Any],
        *,
        expected_source_id: str | None,
        response_url: str | None,
    ) -> dict[str, Any] | None:
        variants = [
            item
            for item in (group.get("hasVariant") or [])
            if isinstance(item, dict)
        ]
        variant = self._select_matching_variant(
            variants,
            expected_source_id=expected_source_id,
            response_url=response_url,
        )
        if variant is None and not variants:
            return None

        merged: dict[str, Any] = dict(group)
        if isinstance(variant, dict):
            for key, value in variant.items():
                if value in (None, "", [], {}):
                    continue
                merged[key] = value

        images = self._merge_ordered_values(group.get("image"), (variant or {}).get("image"))
        if images:
            merged["image"] = images

        props = self._merge_additional_properties(
            group.get("additionalProperty"),
            (variant or {}).get("additionalProperty"),
        )
        if props:
            merged["additionalProperty"] = props

        if not merged.get("description") and group.get("description"):
            merged["description"] = group.get("description")
        if not merged.get("name") and group.get("name"):
            merged["name"] = group.get("name")
        if not merged.get("productID") and group.get("productGroupID"):
            merged["productID"] = str(group.get("productGroupID"))

        return merged

    def _select_matching_variant(
        self,
        variants: list[dict[str, Any]],
        *,
        expected_source_id: str | None,
        response_url: str | None,
    ) -> dict[str, Any] | None:
        if not variants:
            return None
        for variant in variants:
            if self._ld_node_matches_page(
                variant,
                expected_source_id=expected_source_id,
                response_url=response_url,
            ):
                return variant
        for variant in variants:
            if variant.get("offers") or variant.get("additionalProperty") or variant.get("image"):
                return variant
        return variants[0]

    def _ld_node_matches_page(
        self,
        node: dict[str, Any] | None,
        *,
        expected_source_id: str | None,
        response_url: str | None,
    ) -> bool:
        if not isinstance(node, dict):
            return False
        if expected_source_id:
            node_source_id = self._source_id_from_ld(node)
            if node_source_id and node_source_id == expected_source_id:
                return True
        if response_url:
            node_url = str(node.get("url") or node.get("@id") or "").strip()
            if node_url and self._normalize_ld_url(node_url) == self._normalize_ld_url(response_url):
                return True
        return False

    def _normalize_ld_url(self, url: str) -> str:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        normalized_query = ""
        if "skuId" in query and query["skuId"]:
            normalized_query = urlencode({"skuId": query["skuId"][0]})
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", normalized_query, ""))

    def _discovery_mode(self) -> str:
        # Default to hybrid discovery so bounded runs can reach larger, stable
        # product volumes without requiring CLI overrides.
        raw = str(getattr(self, "discovery_mode", "hybrid") or "hybrid").strip().lower()
        if raw in {"homepage", "categories", "hybrid"}:
            return raw
        return "hybrid"

    def _merge_ordered_values(self, *values: Any) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for value in values:
            if isinstance(value, str):
                candidates = [value]
            elif isinstance(value, list):
                candidates = value
            else:
                candidates = []
            for candidate in candidates:
                if isinstance(candidate, dict):
                    text = str(candidate.get("url") or candidate.get("@id") or "").strip()
                else:
                    text = str(candidate or "").strip()
                if not text or text in seen:
                    continue
                seen.add(text)
                out.append(text)
        return out

    def _merge_additional_properties(self, *property_values: Any) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for value in property_values:
            if not isinstance(value, list):
                continue
            for entry in value:
                if not isinstance(entry, dict):
                    continue
                key = re.sub(r"\s+", " ", str(entry.get("name") or "")).strip()
                raw_value = re.sub(r"\s+", " ", str(entry.get("value") or "")).strip()
                if not key or not raw_value:
                    continue
                identity = (key.lower(), raw_value)
                if identity in seen:
                    continue
                seen.add(identity)
                merged.append(entry)
        return merged
