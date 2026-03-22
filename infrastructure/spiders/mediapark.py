from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import scrapy

from infrastructure.spiders.base import BaseProductSpider

# RU labels commonly used on mediapark.uz PDP JSON → domain/schema field names
# (StructuredExtractor also resolves RU aliases; this map is the single source for this spider.)
SPEC_FIELD_MAP: dict[str, str] = {
    "диагональ экрана": "display_size_inch",
    "разрешение экрана": "display_resolution",
    "разрешение": "display_resolution",
    "тип экрана": "display_type",
    "технология экрана": "display_tech",
    "частота развертки экрана": "refresh_rate_hz",
    "оперативная память": "ram_gb",
    "озу": "ram_gb",
    "встроенная память": "storage_gb",
    "внутренняя память": "storage_gb",
    "процессор": "processor",
    "модель процессора": "processor",
    "частота процессора": "processor",
    "основная камера": "main_camera_mp",
    "фронтальная камера": "front_camera_mp",
    "емкость аккумулятора": "battery_mah",
    "ёмкость аккумулятора": "battery_mah",
    "количество sim-карт": "sim_count",
    "количество sim карт": "sim_count",
    "nfc": "nfc",
    "вес": "weight_g",
    "операционная система": "os",
    "беспроводные интерфейсы": "has_wifi",
    "стандарт wi-fi": "has_wifi",
    "версия bluetooth": "has_bluetooth",
    "объем оперативной памяти": "ram_gb",
    "объём оперативной памяти": "ram_gb",
    "тип sim-карты": "sim_count",
    "тип sim карты": "sim_count",
    "защита от пыли и влаги": "os",
    "габариты": "weight_g",
    "видеопроцессор": "gpu",
    "объем жесткого диска": "storage_gb",
    "объём жесткого диска": "storage_gb",
    "тип видеокарты": "gpu",
    "разъемы": "hdmi",
    "hdmi": "hdmi",
    "smart tv": "smart_tv",
    "разрешение (пиксели)": "resolution",
    "диагональ": "display_size_inch",
    "потребляемая мощность": "power_w",
    "класс энергопотребления": "energy_class",
    "цвет": "color",
    "гарантия": "warranty_months",
    "общий объем": "volume_l",
    "общий объём": "volume_l",
}

_RSC_SPEC_PAIR_RE = re.compile(
    r'"name"\s*:\s*\{\s*"uz"\s*:\s*"[^"]*"\s*,\s*"ru"\s*:\s*"([^"]+)"\s*,\s*"kr"\s*:\s*"[^"]*"\s*\}\s*,\s*'
    r'"choices"\s*:\s*\[\s*\{\s*"id"\s*:\s*"[^"]+"\s*,\s*"name"\s*:\s*\{\s*"uz"\s*:\s*"[^"]*"\s*,\s*"ru"\s*:\s*"([^"]+)"',
    re.DOTALL,
)

_VIEW_PATH_RE = re.compile(r"/products/view/[a-z0-9-]+-\d+", re.I)
_STOCK_OUT_PATTERNS = re.compile(
    r"нет\s+в\s+наличии|недоступен\s+к\s+заказу|out\s+of\s+stock|schema\.org/OutOfStock",
    re.I,
)
_TITLE_SKIP_WORDS = frozenset(
    {
        "смартфон",
        "smartphone",
        "телефон",
        "телевизор",
        "ноутбук",
        "ультрабук",
        "планшет",
        "холодильник",
        "стиральная",
        "машина",
        "микроволновая",
        "печь",
        "наушники",
    },
)


class MediaparkSpider(BaseProductSpider):
    name = "mediapark"
    store_name = "mediapark"
    allowed_domains = ["mediapark.uz"]

    custom_settings = {
        **BaseProductSpider.custom_settings,
        "DOWNLOAD_DELAY": 1.0,
    }

    def start_category_urls(self) -> tuple[str, ...]:
        return (
            "https://mediapark.uz/products/category/telefony-17/smartfony-40",
            "https://mediapark.uz/products/category/noutbuki-i-ultrabuki-22/noutbuki-313",
            "https://mediapark.uz/products/category/televizory-i-smart-televizory-8/televizory-307",
            "https://mediapark.uz/products/category/planshety-21/planshety-na-android-78",
            "https://mediapark.uz/products/category/vse-holodilniki-892/holodilniki-62",
            "https://mediapark.uz/products/category/stiralnye-i-sushilnye-mashiny-735/stiralnye-mashiny-70",
        )

    def is_product_page(self, response: scrapy.http.Response) -> bool:
        return "/products/view/" in response.url

    def extract_listing_product_urls(self, response: scrapy.http.Response) -> list[str]:
        return [response.urljoin(p) for p in self._extract_view_paths(response)]

    def extract_next_page_url(self, response: scrapy.http.Response) -> str | None:
        return self.get_next_page(response)

    def extract_source_id_from_url(self, url: str) -> str | None:
        sid = self._extract_external_id(url)
        return sid or None

    def extract_category_hint(
        self,
        response_or_url: scrapy.http.Response | str,
        title: str | None = None,
    ) -> str | None:
        u = response_or_url.url if hasattr(response_or_url, "url") else str(response_or_url)
        return self._category_hint_for_url(u, (title or "").strip())

    @staticmethod
    def _extract_view_paths(response: scrapy.http.Response) -> list[str]:
        text = response.text
        hrefs = set(response.css('a[href*="/products/view/"]::attr(href)').getall())
        hrefs |= set(re.findall(r'"/products/view/[^"]+"', text))
        hrefs |= set(re.findall(r"https://mediapark\.uz/products/view/[a-z0-9-]+-\d+", text, re.I))
        paths: list[str] = []
        for h in hrefs:
            h = h.strip('"')
            h = h.replace("https://mediapark.uz", "")
            if not h.startswith("/"):
                continue
            if _VIEW_PATH_RE.search(h):
                paths.append(h.split("?")[0])
        return sorted(set(paths))

    def get_next_page(self, response: scrapy.http.Response) -> str | None:
        paths = self._extract_view_paths(response)
        if not paths:
            return None
        parsed = urlparse(response.url)
        qs = parse_qs(parsed.query)
        page = 1
        if qs.get("page") and qs["page"][0].isdigit():
            page = int(qs["page"][0])
        qs_clear = {k: v for k, v in qs.items() if k != "page"}
        qs_clear["page"] = [str(page + 1)]
        new_query = urlencode({k: v[0] for k, v in qs_clear.items()})
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", new_query, ""))

    def full_parse_item(self, response: scrapy.http.Response) -> dict[str, Any] | None:
        if "/products/view/" not in response.url:
            return None
        ld = self._parse_product_ld(response)
        if not ld:
            self.logger.warning("[MEDIAPARK] No JSON-LD Product for %s", response.url)
            return None

        title = str(ld.get("name") or "").strip()
        offers = ld.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        price = offers.get("price")
        price_str = str(price).strip() if price is not None else ""
        avail = str(offers.get("availability", "")).lower()
        in_stock = "outofstock" not in avail and "discontinued" not in avail
        if _STOCK_OUT_PATTERNS.search(response.text):
            in_stock = False

        old_price = self._extract_crossed_price(response)
        if old_price and price_str:
            price_str = f"{price_str} (было {old_price})"

        brand = self._brand_from_title(title)
        external_id = self._extract_external_id(response.url)

        raw_specs: dict[str, Any] = {}
        raw_specs.update(self._specs_from_rsc(response))
        raw_specs.update(self._specs_from_tables(response))

        css_srcs = response.css("img.product-image::attr(src), img::attr(data-src)").getall()
        css_urls = [
            urljoin(response.url, src.strip())
            for src in css_srcs
            if src and not str(src).strip().startswith("data:")
        ]
        collected = self._collect_image_urls(response, ld)
        merged: list[str] = []
        seen_u: set[str] = set()
        for u in css_urls + collected:
            if u not in seen_u:
                seen_u.add(u)
                merged.append(u)
        image_urls = merged

        category_hint = self._category_hint_for_url(response.url, title)

        return {
            "url": response.url,
            "title": title,
            "name": title,
            "brand": brand,
            "source_id": external_id,
            "external_id": external_id,
            "price_str": price_str,
            "in_stock": in_stock,
            "raw_specs": raw_specs,
            "image_urls": image_urls,
            "description": str(ld.get("description") or ""),
            "category_hint": category_hint,
        }

    def _category_hint_for_url(self, url: str, title: str) -> str | None:
        u = url.lower()
        t = title.lower()
        if "noutbuk" in u or "ultrabuk" in u or "ноутбук" in t or "ультрабук" in t:
            return "laptop"
        if "televizor" in u or "телевизор" in t:
            return "tv"
        if any(x in u for x in ("holodilnik", "stiral", "split", "konditsioner")):
            return "appliance"
        if any(x in t for x in ("холодильник", "стиральн", "кондиционер", "посудомоечн")):
            return "appliance"
        if "planshet" in u or "планшет" in t:
            return "phone"
        return None

    @staticmethod
    def _parse_product_ld(response: scrapy.http.Response) -> dict[str, Any] | None:
        blocks = re.findall(
            r'<script[^>]*type="application/ld\+json"[^>]*>([\s\S]*?)</script>',
            response.text,
            re.I,
        )
        for raw_json in blocks:
            raw_json = raw_json.strip()
            if not raw_json:
                continue
            try:
                data = json.loads(raw_json)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and data.get("@type") == "Product":
                return data
            if isinstance(data, list):
                for el in data:
                    if isinstance(el, dict) and el.get("@type") == "Product":
                        return el
        return None

    def _extract_external_id(self, url: str) -> str:
        match = re.search(r"/(\d+)(?:$|/|\?)", url)
        if match:
            return match.group(1)
        path = urlparse(url).path.rstrip("/")
        m = re.search(r"-(\d+)$", path)
        return m.group(1) if m else path.rsplit("/", 1)[-1]

    @staticmethod
    def _brand_from_title(title: str) -> str:
        for part in re.split(r"[\s/]+", title):
            p = part.strip()
            if not p:
                continue
            low = p.lower()
            if low in _TITLE_SKIP_WORDS or low.isdigit():
                continue
            return p
        return ""

    def _specs_from_rsc(self, response: scrapy.http.Response) -> dict[str, str]:
        blob = self._next_f_blob(response)
        out: dict[str, str] = {}
        for label, value in _RSC_SPEC_PAIR_RE.findall(blob):
            label_clean = re.sub(r"\s+", " ", label.replace("\t", " ")).strip()
            value_clean = re.sub(r"\s+", " ", value.replace("\t", " ")).strip()
            if len(label_clean) < 2 or not value_clean:
                continue
            if label_clean not in out:
                out[label_clean] = value_clean
        return out

    @staticmethod
    def _next_f_blob(response: scrapy.http.Response) -> str:
        chunks = re.findall(r'self\.__next_f\.push\(\[1,"([\s\S]*?)"\]\)', response.text)
        parts: list[str] = []
        for c in chunks:
            parts.append(
                c.replace("\\n", "\n")
                .replace('\\"', '"')
                .replace("\\\\", "\\")
            )
        return "\n".join(parts)

    def _specs_from_tables(self, response: scrapy.http.Response) -> dict[str, str]:
        rows: dict[str, str] = {}
        for tr in response.css("table tr"):
            cells = [t.strip() for t in tr.css("td, th").xpath("string(.)").getall() if t.strip()]
            if len(cells) >= 2:
                label, value = cells[0], cells[1]
                label = re.sub(r"\s+", " ", label.replace("\t", " ")).strip()
                value = re.sub(r"\s+", " ", value.replace("\t", " ")).strip()
                if label and value:
                    rows.setdefault(label, value)
        return rows

    @staticmethod
    def _extract_crossed_price(response: scrapy.http.Response) -> str | None:
        for m in re.finditer(
            r"(?:line-through|line\-through)[^>]{0,120}>([^<]{1,40}\d[^<]{0,40})",
            response.text,
            re.I,
        ):
            frag = re.sub(r"\s+", " ", m.group(1)).strip()
            digits = re.sub(r"[^\d]", "", frag)
            if len(digits) >= 5:
                return frag
        return None

    def _collect_image_urls(self, response: scrapy.http.Response, ld: dict[str, Any]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []

        def add(u: str) -> None:
            u = u.strip()
            if not u or u in seen:
                return
            if "cdn.mediapark.uz" not in u and "/imgs/" not in u:
                return
            if u.endswith((".svg", ".ico")):
                return
            seen.add(u)
            ordered.append(u)

        raw_img = ld.get("image")
        if isinstance(raw_img, str):
            add(urljoin(response.url, raw_img))
        elif isinstance(raw_img, list):
            for im in raw_img:
                if isinstance(im, str):
                    add(urljoin(response.url, im))
        for attr in ("data-src", "data-lazy-src", "data-original", "src"):
            for u in response.css(f"img::attr({attr})").getall():
                if u:
                    add(response.urljoin(u))
        return ordered
