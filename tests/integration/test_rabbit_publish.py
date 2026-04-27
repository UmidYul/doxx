"""End-to-end outbox publish check: crawl one item, persist to scraper DB, publish via standalone service.

Prerequisites:
  1. RabbitMQ reachable (for example ``docker compose up -d rabbitmq`` from repo root).
  2. ``set MOSCRAPER_INTEGRATION_RABBIT=1`` (Windows) / ``export MOSCRAPER_INTEGRATION_RABBIT=1`` (Unix).
  3. Network access to mediapark.uz (the spider fetches a real listing).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import orjson
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _rabbit_url() -> str:
    return os.environ.get(
        "MOSCRAPER_INTEGRATION_RABBITMQ_ADMIN_URL",
        "amqp://moscraper_admin:moscraper_admin_2026_secure@127.0.0.1:5672/moscraper",
    )


def _publisher_url() -> str:
    return os.environ.get(
        "MOSCRAPER_INTEGRATION_RABBITMQ_PUBLISHER_URL",
        "amqp://moscraper_publisher:moscraper_publisher_2026_secure@127.0.0.1:5672/moscraper",
    )


def _pika_connect_params():
    import pika

    params = pika.URLParameters(_rabbit_url())
    params.socket_timeout = 5.0
    return params


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("MOSCRAPER_INTEGRATION_RABBIT") != "1",
    reason="Set MOSCRAPER_INTEGRATION_RABBIT=1 and start RabbitMQ (see module docstring).",
)
def test_mediapark_crawl_outbox_then_publish_to_bound_queue(tmp_path: Path) -> None:
    import pika
    from domain.publication_event import ScraperProductEvent

    url = _rabbit_url()
    qname = f"moscraper_itest_{uuid.uuid4().hex[:12]}"
    exchange = "moscraper.events"
    routing_key = "listing.scraped.v1"
    db_path = tmp_path / "scraper.db"

    setup = pika.BlockingConnection(_pika_connect_params())
    try:
        ch = setup.channel()
        ch.exchange_declare(exchange=exchange, exchange_type="topic", durable=True)
        ch.queue_declare(queue=qname, durable=False, exclusive=False, auto_delete=False)
        ch.queue_bind(queue=qname, exchange=exchange, routing_key=routing_key)
    finally:
        setup.close()

    env = os.environ.copy()
    env["RABBITMQ_URL"] = _publisher_url()
    env["RABBITMQ_EXCHANGE"] = exchange
    env["RABBITMQ_EXCHANGE_TYPE"] = "topic"
    env["RABBITMQ_ROUTING_KEY"] = routing_key
    env["RABBITMQ_PUBLISH_MANDATORY"] = "true"
    env["RABBITMQ_DECLARE_TOPOLOGY"] = "false"
    env["SCRAPER_DB_BACKEND"] = "sqlite"
    env["SCRAPER_DB_PATH"] = str(db_path)

    crawl = subprocess.run(
        [
            sys.executable,
            "-m",
            "scrapy",
            "crawl",
            "mediapark",
            "-s",
            "CLOSESPIDER_ITEMCOUNT=1",
            "-s",
            "LOG_LEVEL=ERROR",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=240,
    )
    if crawl.returncode != 0:
        pytest.skip(f"mediapark crawl failed (network or site drift). stderr tail:\n{crawl.stderr[-2500:]!s}")

    publish = subprocess.run(
        [
            sys.executable,
            "-m",
            "services.publisher.main",
            "--once",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert publish.returncode == 0, publish.stderr or publish.stdout

    read = pika.BlockingConnection(_pika_connect_params())
    try:
        rh = read.channel()
        method = None
        body = None
        for _ in range(30):
            method, _properties, body = rh.basic_get(queue=qname, auto_ack=True)
            if method is not None:
                break
            time.sleep(1.0)
        else:
            pytest.fail("no message arrived in bound queue within 30s after outbox publish")
    finally:
        try:
            ch_del = read.channel()
            ch_del.queue_delete(queue=qname, if_unused=False, if_empty=False)
        except Exception:
            pass
        read.close()

    assert body is not None
    payload = orjson.loads(body)
    event = ScraperProductEvent.model_validate(payload)
    assert event.event_type == "scraper.product.scraped.v1"
    assert event.schema_version == 1
    assert event.store_name == "mediapark"
    assert event.source_url.startswith("http")
    assert event.payload_hash.startswith("sha256:")
    assert event.structured_payload.store_name == "mediapark"
    assert event.publication.publisher_service
