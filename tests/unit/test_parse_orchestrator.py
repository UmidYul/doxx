from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from application.parse_orchestrator import run_spider


def test_run_spider_starts_crawler_process(mocker):
    process_cls = mocker.patch("application.parse_orchestrator.CrawlerProcess")
    mocker.patch(
        "application.parse_orchestrator.get_project_settings",
        return_value=MagicMock(),
    )
    instance = process_cls.return_value

    run_spider("mediapark")

    process_cls.assert_called_once()
    instance.crawl.assert_called_once_with("mediapark")
    instance.start.assert_called_once()


def test_run_spider_applies_settings_overrides(mocker):
    process_cls = mocker.patch("application.parse_orchestrator.CrawlerProcess")
    settings = MagicMock()
    mocker.patch("application.parse_orchestrator.get_project_settings", return_value=settings)
    instance = process_cls.return_value

    run_spider("mediapark", settings_overrides={"LOG_LEVEL": "DEBUG"})

    settings.update.assert_called_once()
    instance.crawl.assert_called_once_with("mediapark")
