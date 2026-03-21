from __future__ import annotations

# Manual / future canary runs: fetch URL and assert on normalized listing fields (not CRM specs).
CANARY_PRODUCTS = {
    "mediapark": {
        "url": "https://mediapark.uz/products/view/smartfon-samsung-galaxy-z-flip-7-black-12-256-32771",
        "store": "mediapark",
        "assertions": {
            "brand": "Samsung",
            "price_value": lambda v: v is not None and 5_000_000 < v < 40_000_000,
            "raw_specs": lambda d: isinstance(d, dict) and len(d) >= 3,
        },
    },
}
