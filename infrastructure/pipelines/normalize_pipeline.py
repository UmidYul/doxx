from __future__ import annotations

from decimal import Decimal

from application.extractors.spec_extractor import extract_specs
from application.extractors.unit_normalizer import normalize_brand, normalize_price
from domain.normalized_product import NormalizedProduct


class NormalizePipeline:
    async def process_item(self, item, spider):
        if "discovered_url" in item:
            return item

        price = normalize_price(item.get("price_str"))
        if price is None:
            price = Decimal("0")

        brand = normalize_brand(item.get("brand", ""))
        category = item.get("category")
        title = item.get("title") or item.get("name", "")

        raw_specs = item.get("raw_specs", {})
        description = item.get("description", "")
        specs = await extract_specs(raw_specs, description, category, title)

        normalized = NormalizedProduct(
            source=item.get("source", spider.store_name),
            url=item["url"],
            source_id=item.get("source_id", ""),
            brand=brand or "",
            name=title,
            price=price,
            currency=item.get("currency", "UZS"),
            in_stock=item.get("in_stock", True),
            specs=specs,
            images=item.get("image_urls", []),
            extraction_method=specs.extraction_method,
            completeness_score=specs.completeness_score,
        )

        item["_normalized"] = normalized
        return item
