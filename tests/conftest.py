from __future__ import annotations

import pytest

from domain.raw_product import RawProduct


@pytest.fixture
def sample_raw_product() -> RawProduct:
    return RawProduct(
        source="mediapark",
        url="https://mediapark.uz/product/samsung-galaxy-s24-ultra",
        source_id="samsung-galaxy-s24-ultra",
        title="Samsung Galaxy S24 Ultra 12/256GB Titanium Black",
        price_str="17 990 000 сум",
        in_stock=True,
        raw_specs={
            "Оперативная память": "12 ГБ",
            "Встроенная память": "256 ГБ",
        },
        image_urls=["https://mediapark.uz/img/samsung-s24-ultra-1.jpg"],
        description="Новый Samsung Galaxy S24 Ultra",
    )
