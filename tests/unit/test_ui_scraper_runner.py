from __future__ import annotations

from services.ui_api.run_registry import RunRegistry
from services.ui_api.scraper_runner import ScraperRunner, StartRunRequest


def test_build_command_passes_targeting_args(tmp_path):
    runner = ScraperRunner(registry=RunRegistry(tmp_path / "runs.json"), repo_root=tmp_path)

    command = runner._build_command(
        StartRunRequest(
            store="alifshop",
            item_limit=5,
            category="phone",
            brand="iPhone",
            category_url="https://alifshop.uz/ru/categories/smartfoni-apple",
        )
    )

    assert "-a" in command
    assert "category=phone" in command
    assert "brand=iPhone" in command
    assert "category_url=https://alifshop.uz/ru/categories/smartfoni-apple" in command

