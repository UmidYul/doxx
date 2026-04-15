"""Shared product classifier used by all Moscraper store spiders.

Single source of truth for:
  - Category inference  (URL slug → title keywords → brand heuristic)
  - Brand extraction    (JSON-LD brand → known-brand lookup → title first-word)
  - Uzum category gating (keep only electronics/appliance category URLs)
"""
from __future__ import annotations

import re

from application.normalization.category_inference import infer_category_hint

# ---------------------------------------------------------------------------
# Brand knowledge base
# ---------------------------------------------------------------------------

# Phone-primary brands (rarely make anything else sold in UZ electronics stores)
_PHONE_BRANDS: frozenset[str] = frozenset({
    "nothing", "infinix", "tecno", "itel", "meizu", "zte", "fly",
    "alcatel", "blackview", "oukitel", "doogee", "umidigi", "cubot",
    "ulefone", "realme", "oppo", "vivo", "oneplus", "poco", "redmi",
    "honor", "novey", "benco", "micromax", "lava", "karbonn",
    "coolpad", "wiko", "cat", "agm", "oscal", "hotwav", "hmd",
    "iphone",  # often title starts with "iPhone" without brand "Apple"
})

# Multi-category brands: can be phone OR laptop OR TV
# key = lowercase brand name, values = categories that brand covers
_MULTI_BRANDS: dict[str, tuple[str, ...]] = {
    "apple":    ("phone", "laptop"),  # iPhone dominant; check for Mac keywords
    "samsung":  ("phone", "tv", "appliance", "laptop"),
    "xiaomi":   ("phone", "tv", "laptop", "appliance"),
    "lg":       ("phone", "tv", "appliance"),
    "sony":     ("phone", "tv"),
    "huawei":   ("phone", "laptop"),
    "nokia":    ("phone",),           # mostly phones now
    "motorola": ("phone",),
    "google":   ("phone",),           # Pixel phones
    "asus":     ("phone", "laptop", "gaming"),
    "lenovo":   ("phone", "laptop"),
    "microsoft":("laptop",),          # Surface
    "dell":     ("laptop",),
    "hp":       ("laptop",),
    "acer":     ("laptop",),
    "msi":      ("laptop", "gaming"),
    "gigabyte": ("laptop", "gaming"),
    "razer":    ("laptop", "gaming"),
    "toshiba":  ("laptop", "tv", "appliance"),
    "fujitsu":  ("laptop",),
    "philips":  ("tv", "appliance"),
    "hisense":  ("tv", "appliance"),
    "tcl":      ("tv",),
    "artel":    ("tv", "appliance"),
    "sharp":    ("tv", "appliance"),
    "panasonic":("tv", "appliance"),
    "haier":    ("tv", "appliance"),
    "beko":     ("appliance",),
    "vestel":   ("appliance",),
    "indesit":  ("appliance",),
    "bosch":    ("appliance",),
    "siemens":  ("appliance",),
    "electrolux":("appliance",),
    "whirlpool":("appliance",),
}

# Flat set of ALL known brands for fast lookup
_ALL_KNOWN_BRANDS: frozenset[str] = frozenset(_PHONE_BRANDS) | frozenset(_MULTI_BRANDS)

# Smaller appliance / regional brands often absent from JSON-LD — match by title token
_EXTRA_BRANDS: frozenset[str] = frozenset({
    "goodwell", "hofmann", "gorenje", "candy", "smeg", "miele", "novey",
    "kuppersberg", "maunfeld", "luxor", "shivaki", "davoline", "hansa",
    "pyramida", "simfer", "minola", "ferre", "weissgauff",
})

# ---------------------------------------------------------------------------
# Category keyword sets
# ---------------------------------------------------------------------------

# URL path slug fragments → category
_URL_MAP: list[tuple[frozenset[str], str]] = [
    (frozenset({"smartfon", "telefon", "smartphone", "smartfonlar", "smartfonyi",
                "mobile-phone", "smartfony", "smartfonov", "phone"}), "phone"),
    (frozenset({"noutbuk", "laptop", "ultrabuk", "notebook", "noutbuki", "ultrabuki",
                "noutbukov"}), "laptop"),
    (frozenset({"televizor", "televizory", "television", "smart-tv", "tv-",
                "oled", "qled"}), "tv"),
    (frozenset({"planshet", "planshety", "tablet", "ipad"}), "tablet"),
    (frozenset({"monitor", "monitori", "display"}), "monitor"),
    (frozenset({"holodilnik", "holodilniki", "kholodilnik", "stiral", "stiralnye",
                "konditsioner", "konditsionery", "split-sistem", "pylesoc", "pylesosy",
                "mikrovolnovka", "plita", "plity", "posudomoechnaya", "duhovka",
                "duhovoy", "duhovye", "duhovoy-shkaf", "duhovye-shkafy", "vstraivaem",
                "vstroen", "bytovaya-tehnika", "vstraivaemaya-tehnika",
                "refrigerator", "washing-machine", "air-conditioner", "oven"}), "appliance"),
    # Mediapark: smartphones/tablets by brand hub
    (frozenset({"smartfony-po-brendu", "smartfony-samsung", "smartfony-xiaomi",
                "smartfony-huawei", "smartfony-apple", "smartfony-iphone",
                "smartfony-vivo", "smartfony-oppo", "smartfony-honor", "smartfony-realme",
                "smartfony-infinix", "smartfony-tecno", "smartfony-nothing"}), "phone"),
    (frozenset({"planshety-po-brendu", "planshety-samsung", "planshety-apple"}), "tablet"),
    (frozenset({"naushniki", "naushnik", "zaryadka", "zaryadnoe", "aksessuary",
                "aksessuari", "powerbank", "chehol", "kabel", "headphones",
                "earphones", "gadzhet", "gadzhety"}), "accessory"),
    (frozenset({"igrovye", "igrovaya", "gaming", "pristavki", "gamepad",
                "controller"}), "gaming"),
]

# Title keyword sets (lowercase match anywhere in the title)
_TITLE_MAP: list[tuple[frozenset[str], str]] = [
    (frozenset({"смартфон", "smartphone", "phone", "мобильный телефон"}), "phone"),
    (frozenset({"ноутбук", "ультрабук", "laptop", "notebook"}), "laptop"),
    (frozenset({"телевизор", "television", "tv"}), "tv"),
    (frozenset({"планшет", "tablet"}), "tablet"),
    (frozenset({"монитор", "monitor"}), "monitor"),
    (frozenset({"холодильник", "стиральная", "стиральные", "кондиционер",
                "посудомоечная", "микроволновая", "пылесос", "духовка", "вытяжка",
                "духовой шкаф", "духовой", "варочная панель", "варочная", "плита газовая",
                "встраиваемая техника", "встраиваемая",
                "washing machine", "refrigerator", "air conditioner", "built-in oven", "oven"}), "appliance"),
    (frozenset({"наушники", "гарнитура", "чехол", "зарядное", "кабель",
                "powerbank", "bluetooth колонка", "headphones", "earphones",
                "earbuds", "tws", "автодержатель", "держатель",
                "радиотелефон", "стационарный телефон"}), "accessory"),
    (frozenset({"игровой", "игровые", "геймпад", "джойстик", "gamepad",
                "controller", "playstation", "xbox", "nintendo"}), "gaming"),
]

# TV context signals (help disambiguate multi-brand products)
_TV_SIGNALS: frozenset[str] = frozenset({
    "телевизор", "television", "smart tv", "4k", "8k", "qled", "oled",
    'дюйм', 'inch', '"', "'", "hdr", "uhd", "fhd", "curved tv",
})

# Laptop context signals
_LAPTOP_SIGNALS: frozenset[str] = frozenset({
    "ноутбук", "laptop", "notebook", "macbook", "mac book",
    "ultrabook", "ультрабук",
})


# Non-smartphone products that may appear on smartphone listing pages
_NOT_SMARTPHONE_TITLE_KW: frozenset[str] = frozenset({
    "радиотелефон", "автодержатель", "держатель для телефона",
    "стационарный телефон", "проводной телефон", "кнопочный телефон",
    "селфи-палка", "штатив", "стилус", "sim-карта",
})

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_category(
    url: str,
    title: str,
    ld_category: str | None = None,
) -> str:
    """Classify a product into a category string.

    Returns one of: phone, laptop, tv, tablet, monitor, appliance, accessory,
    gaming, unknown.

    Priority: shared deterministic inference > brand heuristic fallback.
    """
    inferred = infer_category_hint(url, title, {}, spider_hint=ld_category)
    if inferred != "unknown":
        return inferred

    t = title.lower().strip()

    # Brand-based heuristic stays as a last resort for model-only titles.
    first = _first_word(title)
    if first:
        if first in _PHONE_BRANDS:
            return "phone"
        if first in _MULTI_BRANDS:
            cats = _MULTI_BRANDS[first]
            if len(cats) == 1:
                return cats[0]
            # Disambiguate with context signals in the title
            if "laptop" in cats and any(s in t for s in _LAPTOP_SIGNALS):
                return "laptop"
            if "tv" in cats and _has_tv_signal(t):
                return "tv"
            if "appliance" in cats and any(
                s in t for s in ("холодильник", "стиральн", "кондиционер",
                                  "пылесос", "духовка", "духовой", "шкаф",
                                  "refrigerator", "washing", "dishwasher")
            ):
                return "appliance"
            # Default to first category in the brand's list
            return cats[0]

    return "unknown"


def extract_brand(title: str, ld_brand: str | None = None) -> str:
    """Extract the product brand.

    Priority:
      1. Explicit JSON-LD brand field (most authoritative)
      2. Any title token matching known / extra brand dictionary (handles
         \"Духовой шкаф Haier ...\", \"Чехол для Samsung ...\")
      3. First non-generic word in the title
    """
    # 1. JSON-LD brand
    if ld_brand and ld_brand.strip():
        return ld_brand.strip()

    all_brands = _ALL_KNOWN_BRANDS | _EXTRA_BRANDS
    tokens = [t for t in re.split(r"[\s/\-_]+", title.strip()) if t.strip()]

    # 2. Prefer a known brand token anywhere in the title (order: first hit)
    for word in tokens:
        lw = word.lower().strip()
        if len(lw) < 2:
            continue
        if lw in all_brands:
            # Canonical remapping (iPhone → Apple)
            if lw == "iphone":
                return "Apple"
            return word.strip()

    # 3. First non-generic word from title (preserves original casing)
    for word in re.split(r"[\s/]+", title.strip()):
        w = word.strip()
        if not w or len(w) < 2:
            continue
        if w.lower() in _TITLE_SKIP_WORDS:
            continue
        if w.isdigit() or re.match(r"^\d", w):
            continue
        # Parenthetical or RAM/storage-size tokens like "12/256Gb"
        if re.match(r"^\d+[/\-]\d+", w):
            continue
        return w

    return ""


# ---------------------------------------------------------------------------
# Uzum category gating
# ---------------------------------------------------------------------------

# Top-level Uzum categories we want to crawl (electronics + appliances)
_UZUM_ALLOWED_ROOT_SLUGS: frozenset[str] = frozenset({
    "elektronika",
    "bytovaya-tekhnika",
})

# Sub-slug keywords we explicitly allow under those roots
_UZUM_ALLOWED_SUBCAT_KW: frozenset[str] = frozenset({
    "smartfon", "telefon", "noutbuk", "laptop", "planshet", "tablet",
    "televizor", "monitor", "gaming", "igrovye", "aksessuary", "naushniki",
    "gadzhety", "smart-chasy", "smart-bras", "powerbank", "zaryadnoe",
    "kompyuter", "printer", "skaner", "projetor", "foto-video", "fotoappar",
    "videokamer", "holodilnik", "kholodilnik", "stiralny", "konditsioner",
    "split", "pylesosy", "pylesoc", "mikrovolnovk", "plita", "posudomoech",
    "duhovka", "ventilyator", "obogrev", "utyug", "utjug", "elektrobrit",
    "epilyat", "fonendoskop", "mediapleer", "ekshncamer", "dron",
    "elektrosamocat", "giroboard", "videodomofon", "signalizaciya",
    "umnyj-dom", "smart-dom",
    # keep numeric-ID categories that are children of allowed roots
})

# Slug fragments that identify clearly non-electronics Uzum categories
_UZUM_BLOCKED_CAT_KW: frozenset[str] = frozenset({
    "pitaniya", "produkty", "krasota", "zdorove", "apteka",
    "odezhda", "obuv", "aksessuary-odezhdy",  # clothing accessories ≠ gadget accessories
    "sport", "turizm", "velosipedy",
    "dom-i-sad", "sad-i-ogorod", "stroitelstvo",
    "igrushki", "detskie", "mama",
    "avtomobili", "avto", "shinyi", "diski-i-shin",
    "knigi", "kancelyariya", "shkola",
    "muzykalnye", "muzykalny",
    "zhivotny", "zoo",
    "proczessori",  # not blocking processors — but the slug "proczessori" is Uzbek
})


def is_electronics_category_url(url: str) -> bool:
    """Return True if an Uzum category URL should be followed during crawl.

    Allows root electronics/appliance categories and their sub-categories.
    Explicitly blocks food, clothing, beauty, etc.
    """
    path = urlparse_path(url).lower()
    # Must be a /category/ path
    if "/category/" not in path:
        return False
    # Reject anything matching a blocked keyword
    if any(kw in path for kw in _UZUM_BLOCKED_CAT_KW):
        return False
    # Allow known electronics root slugs
    if any(kw in path for kw in _UZUM_ALLOWED_ROOT_SLUGS):
        return True
    # Allow sub-categories matching electronics keywords
    if any(kw in path for kw in _UZUM_ALLOWED_SUBCAT_KW):
        return True
    # Conservative default for Uzum: skip uncategorised paths
    # (better to miss a category than to scrape food/clothes)
    return False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Words that are generic category labels, not brand names
_TITLE_SKIP_WORDS: frozenset[str] = frozenset({
    "смартфон", "smartphone", "телефон", "телевизор", "ноутбук", "ультрабук",
    "планшет", "холодильник", "стиральная", "стиральные", "машина", "машины",
    "микроволновая", "печь", "наушники", "монитор", "компьютер", "системный",
    "блок", "аккумулятор", "зарядное", "зарядка", "чехол", "кабель",
    "powerbank", "колонка", "гарнитура", "игровой", "игровые",
    "мобильный", "беспроводные", "умные", "часы",
    # Product-type prefixes (brand often follows)
    "духовой", "шкаф", "встраиваемая", "встраиваемый", "газовая", "газовый",
    "электрическая", "электрический", "настольная", "комбинированная",
    "для",
})


def _first_word(title: str) -> str:
    """Return first meaningful lowercase word from title."""
    for word in re.split(r"[\s/\-_]+", title.strip()):
        w = word.strip().lower()
        if w and len(w) >= 2 and w not in _TITLE_SKIP_WORDS and not w.isdigit():
            return w
    return ""


def _has_tv_signal(title_lower: str) -> bool:
    """Check if the lowercased title contains TV-specific context signals."""
    # Numeric inch pattern: 32", 55"  etc.
    if re.search(r'\b\d{2,3}\s*(?:дюйм|inch|")', title_lower):
        return True
    return any(s in title_lower for s in _TV_SIGNALS)


def urlparse_path(url: str) -> str:
    """Extract just the URL path component."""
    try:
        from urllib.parse import urlparse as _up
        return _up(url).path
    except Exception:
        return url
