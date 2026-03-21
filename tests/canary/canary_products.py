from __future__ import annotations

CANARY_PRODUCTS = {
    "mediapark": {
        "url": "https://mediapark.uz/products/view/smartfon-samsung-galaxy-z-flip-7-black-12-256-32771",
        "store": "mediapark",
        "assertions": {
            "brand": "Samsung",
            "specs.ram_gb": lambda v: v in (8, 12),
            "specs.storage_gb": lambda v: v in (128, 256, 512, 1024),
            "price": lambda v: v is not None and 5_000_000 < v < 40_000_000,
        },
    },
    "uzum": {
        "url": "https://uzum.uz/ru/product/smartfon-samsung-galaxy-a15-4128gb-234001",
        "store": "uzum",
        "assertions": {
            "brand": "Samsung",
            "specs.storage_gb": lambda v: v in (64, 128, 256),
            "price": lambda v: v is not None and 1_000_000 < v < 15_000_000,
        },
    },
}
