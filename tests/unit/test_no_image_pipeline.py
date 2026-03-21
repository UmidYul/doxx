from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"
SCRAPY_SETTINGS = REPO_ROOT / "config" / "scrapy_settings.py"


def test_image_pipeline_module_absent():
    path = REPO_ROOT / "infrastructure" / "pipelines" / "image_pipeline.py"
    assert not path.is_file()


@pytest.mark.parametrize(
    "needle",
    [
        "torch",
        "rembg",
        "pillow",
        "open-clip",
        "torchvision",
        "timm",
        "clip",
    ],
)
def test_pyproject_excludes_image_ml_dependencies(needle: str):
    text = PYPROJECT.read_text(encoding="utf-8").lower()
    assert needle not in text


def test_scrapy_settings_item_pipelines_exclude_image_pipeline():
    text = SCRAPY_SETTINGS.read_text(encoding="utf-8")
    assert "image_pipeline" not in text
    assert "ImagePipeline" not in text
