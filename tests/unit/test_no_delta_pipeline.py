from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRAPY_SETTINGS = REPO_ROOT / "config" / "scrapy_settings.py"


def test_delta_pipeline_module_absent():
    path = REPO_ROOT / "infrastructure" / "pipelines" / "delta_pipeline.py"
    assert not path.is_file()


def test_scrapy_settings_item_pipelines_exclude_delta_pipeline():
    text = SCRAPY_SETTINGS.read_text(encoding="utf-8")
    assert "delta_pipeline" not in text
    assert "DeltaPipeline" not in text
