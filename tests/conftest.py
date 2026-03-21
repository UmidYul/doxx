from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from domain.events import CRMSyncResponse
from domain.normalized_product import NormalizedProduct
from domain.raw_product import RawProduct
from domain.specs.phone import PhoneSpecs


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
            "Ёмкость аккумулятора": "5000 мАч",
            "Диагональ экрана": "6.8 дюймов",
            "Процессор": "Snapdragon 8 Gen 3",
            "Основная камера": "200 Мп",
            "Фронтальная камера": "12 Мп",
            "Операционная система": "Android 14",
            "NFC": "Есть",
            "Количество SIM": "2",
        },
        image_urls=["https://mediapark.uz/img/samsung-s24-ultra-1.jpg"],
        description="Новый Samsung Galaxy S24 Ultra с S-Pen",
    )


@pytest.fixture
def sample_phone_specs() -> PhoneSpecs:
    return PhoneSpecs(
        display_size_inch=6.8,
        display_resolution="3120x1440",
        display_type="Dynamic AMOLED 2X",
        ram_gb=12,
        storage_gb=256,
        battery_mah=5000,
        processor="Snapdragon 8 Gen 3",
        main_camera_mp=200,
        front_camera_mp=12,
        os="Android 14",
        sim_count=2,
        nfc=True,
        weight_g=232,
    )


@pytest.fixture
def sample_normalized_product(sample_phone_specs: PhoneSpecs) -> NormalizedProduct:
    return NormalizedProduct(
        source="mediapark",
        url="https://mediapark.uz/product/samsung-galaxy-s24-ultra",
        source_id="samsung-galaxy-s24-ultra",
        brand="Samsung",
        name="Samsung Galaxy S24 Ultra 12/256GB Titanium Black",
        price=Decimal("17990000"),
        currency="UZS",
        in_stock=True,
        specs=sample_phone_specs,
        images=["https://mediapark.uz/img/samsung-s24-ultra-1.jpg"],
        extraction_method="structured",
        completeness_score=1.0,
    )


@pytest.fixture
def sample_parse_cache():
    """Simulates a ParseCache object (use a simple namespace for unit tests)."""

    class FakeCache:
        url = "https://mediapark.uz/product/samsung-galaxy-s24-ultra"
        source_name = "mediapark"
        source_id = "samsung-galaxy-s24-ultra"
        last_price = Decimal("17990000")
        last_in_stock = True
        last_parsed_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        crm_listing_id = uuid.uuid4()
        crm_product_id = uuid.uuid4()

    return FakeCache()


@pytest.fixture
def mock_crm_response() -> CRMSyncResponse:
    return CRMSyncResponse(
        status="ok",
        crm_listing_id=uuid.uuid4(),
        crm_product_id=uuid.uuid4(),
        action="created",
    )
