from __future__ import annotations

from application.extractors.unit_normalizer import normalize_brand, normalize_price
from domain.normalized_product import NormalizedProduct


class NormalizePipeline:
    """Price/brand cleanup and typing only — no per-spec regex dispatch or LLM (see ``unit_normalizer`` for parsers used elsewhere)."""

    def process_item(self, item, spider):
        title = (item.get("title") or item.get("name") or "").strip()
        price_str = (item.get("price_str") or "").strip()
        price_dec = normalize_price(price_str) if price_str else None
        price = float(price_dec) if price_dec is not None else None

        brand_raw = item.get("brand") or ""
        brand = normalize_brand(brand_raw) if brand_raw else None

        raw_specs = item.get("raw_specs") or {}
        if isinstance(raw_specs, dict):
            coerced: dict[str, str] = {}
            for k, v in raw_specs.items():
                coerced[str(k)] = "" if v is None else str(v).strip()
            raw_specs = coerced
        else:
            raw_specs = {}

        desc = item.get("description")
        description = (desc or "").strip() or None if desc is not None else None

        normalized = NormalizedProduct(
            store=str(item.get("source", spider.store_name)).strip(),
            url=item["url"].strip(),
            title=title,
            source_id=(item.get("source_id") or "").strip() or None,
            price_raw=price_str or None,
            price=price,
            currency=(item.get("currency") or "UZS").strip(),
            in_stock=bool(item.get("in_stock", True)),
            brand=brand,
            raw_specs=raw_specs,
            description=description,
            image_urls=[str(u).strip() for u in (item.get("image_urls") or []) if u],
        )
        item["_normalized"] = normalized.model_dump(mode="json")
        return item
