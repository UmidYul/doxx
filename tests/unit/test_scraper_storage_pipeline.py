from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from config.settings import settings
from infrastructure.pipelines.scraper_storage_pipeline import ScraperStoragePipeline
from infrastructure.persistence.sqlite_store import SQLiteScraperStore


class _FakeStats:
    def __init__(self) -> None:
        self._stats = {
            "finish_reason": "finished",
            "item_scraped_count": 1,
            "item_dropped_count": 0,
        }

    def get_stats(self) -> dict[str, object]:
        return dict(self._stats)


class _FakeSpider:
    name = "mediapark"
    store_name = "mediapark"

    def __init__(self) -> None:
        self.crawler = SimpleNamespace(stats=_FakeStats())

    def start_category_urls(self) -> list[str]:
        return ["https://mediapark.uz/products/category/phones"]


def test_scraper_pipeline_persists_item_and_finishes_run(tmp_path: Path) -> None:
    db_path = tmp_path / "scraper.db"
    original_db_path = settings.SCRAPER_DB_PATH
    settings.SCRAPER_DB_PATH = str(db_path)
    try:
        spider = _FakeSpider()
        pipeline = ScraperStoragePipeline()
        pipeline.open_spider(spider)

        item = pipeline.process_item(
            {
                "source": "mediapark",
                "url": "https://mediapark.uz/products/view/demo-phone-123",
                "source_id": "123",
                "title": "Demo Phone",
                "price_str": "1000000",
                "in_stock": True,
                "brand": "DemoBrand",
                "raw_specs": {"Color": "Black"},
                "image_urls": ["https://mediapark.uz/img/demo.jpg"],
                "description": "Demo description",
                "category_hint": "phone",
            },
            spider,
        )
        pipeline.close_spider(spider)

        run_id = str(item["_scrape_run_id"])
        store = SQLiteScraperStore(db_path)
        run_row = store.get_scrape_run_row(run_id)
        assert run_row is not None
        assert run_row["status"] == "completed"
        assert run_row["items_scraped"] == 1
        assert run_row["items_persisted"] == 1

        product_row = store.get_snapshot_row(scrape_run_id=run_id, identity_key="mediapark:123")
        assert product_row is not None
        assert product_row["source_url"] == "https://mediapark.uz/products/view/demo-phone-123"
        assert product_row["publication_state"] == "pending"

        outbox_row = store.get_outbox_row(str(item["_outbox_event_id"]))
        assert outbox_row is not None
        assert outbox_row["status"] == "pending"
    finally:
        settings.SCRAPER_DB_PATH = original_db_path
