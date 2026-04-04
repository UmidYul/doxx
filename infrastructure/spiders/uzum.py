from __future__ import annotations

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
_UZUM_PRODUCT_PATH_RE = re.compile(r"/(?:ru/)?product/[^/?#]+", re.I)
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
_UZUM_PRIMARY_SMARTPHONE_CATEGORY_URL = "https://uzum.uz/ru/category/smartfony-12690"
_UZUM_LAPTOP_CATEGORY_URL = "https://uzum.uz/ru/category/noutbuki-15718"
_UZUM_TABLET_CATEGORY_URL = "https://uzum.uz/ru/category/planshety-i-elektronnye-knigi-15716"
_UZUM_TV_CATEGORY_URL = "https://uzum.uz/ru/category/televizory-12601"
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
                PageMethod("wait_for_timeout", 1800),
                PageMethod("evaluate", "window.scrollTo(0, Math.min(document.body.scrollHeight, 2500))"),
                PageMethod("wait_for_timeout", 1200),
                PageMethod("evaluate", "window.scrollTo(0, Math.min(document.body.scrollHeight, 5000))"),
                PageMethod("wait_for_timeout", 1200),
                PageMethod("evaluate", "window.scrollTo(0, document.body.scrollHeight)"),
                PageMethod("wait_for_timeout", 2000),
                PageMethod("wait_for_timeout", 2500),
                PageMethod("wait_for_timeout", 5000),
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
