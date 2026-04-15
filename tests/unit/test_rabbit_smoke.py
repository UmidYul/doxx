from __future__ import annotations

from unittest.mock import patch

import pytest

from config.settings import Settings
from infrastructure.observability import message_codes as obs_mc
from scripts import rabbit_smoke


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        RABBITMQ_URL="amqp://moscraper_publisher:test-pass@localhost:5672/moscraper",
        RABBITMQ_EXCHANGE="moscraper.events",
        RABBITMQ_CRM_QUEUE="crm.products.import.v1",
        RABBITMQ_ROUTING_KEY="listing.scraped.v1",
        RABBITMQ_RETRY_EXCHANGE="crm.products.retry",
    )


def test_rabbit_smoke_main_logs_success(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []

    async def _fake_publish_and_read(cfg: Settings, crm_queue: str) -> None:
        called.append(f"{cfg.RABBITMQ_EXCHANGE}:{crm_queue}")

    monkeypatch.setattr(rabbit_smoke, "settings", _settings())
    monkeypatch.setattr(rabbit_smoke, "bootstrap_rabbitmq", lambda cfg: called.append("bootstrapped"))
    monkeypatch.setattr(rabbit_smoke, "_publish_and_read", _fake_publish_and_read)

    with patch("scripts.rabbit_smoke.log_publisher_event") as log_event:
        exit_code = rabbit_smoke.main(["--skip-bootstrap"])

    assert exit_code == 0
    assert called == ["moscraper.events:crm.products.import.v1"]
    log_event.assert_called_once()
    assert log_event.call_args.args[0] == obs_mc.PUBLISHER_SMOKE_COMPLETED


def test_rabbit_smoke_main_logs_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_publish_and_read(cfg: Settings, crm_queue: str) -> None:
        raise OSError("smoke failed")

    monkeypatch.setattr(rabbit_smoke, "settings", _settings())
    monkeypatch.setattr(rabbit_smoke, "bootstrap_rabbitmq", lambda cfg: None)
    monkeypatch.setattr(rabbit_smoke, "_publish_and_read", _fake_publish_and_read)

    with patch("scripts.rabbit_smoke.log_publisher_event") as log_event:
        with pytest.raises(OSError, match="smoke failed"):
            rabbit_smoke.main(["--skip-bootstrap"])

    log_event.assert_called_once()
    assert log_event.call_args.args[0] == obs_mc.PUBLISHER_SMOKE_FAILED
    assert log_event.call_args.kwargs["severity"] == "error"


def test_build_event_uses_final_publication_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rabbit_smoke, "settings", _settings())

    event = rabbit_smoke._build_event(_settings(), "main")

    assert event.publication.outbox_status == "published"
    assert event.publication.publisher_service == "rabbit-smoke"
    assert event.publication.published_at is not None
