"""End-to-end publish check: real broker + one mediapark item.

Prerequisites:
  1. RabbitMQ reachable (e.g. ``docker compose up -d rabbitmq`` from repo root).
  2. ``set MOSCRAPER_INTEGRATION_RABBIT=1`` (Windows) / ``export MOSCRAPER_INTEGRATION_RABBIT=1`` (Unix).
  3. Network access to mediapark.uz (spider fetches a real listing).

Optional: ``MOSCRAPER_INTEGRATION_RABBITMQ_URL`` overrides the broker URL (default ``amqp://guest:guest@127.0.0.1:5672/``).

Run only integration tests::

    pytest tests/integration -m integration -v
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
    return os.environ.get("MOSCRAPER_INTEGRATION_RABBITMQ_URL", "amqp://guest:guest@127.0.0.1:5672/")


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
def test_mediapark_crawl_publishes_cloud_event_to_bound_queue() -> None:
    import pika
    from domain.messages import CloudEventListingScraped

    url = _rabbit_url()
    qname = f"moscraper_itest_{uuid.uuid4().hex[:12]}"
    exchange = "moscraper.events"
    routing_key = "listing.scraped.v1"

    def _declare_bind_and_teardown_queue() -> None:
        c = pika.BlockingConnection(_pika_connect_params())
        try:
            h = c.channel()
            h.queue_delete(queue=qname, if_unused=False, if_empty=False)
        except Exception:
            pass
        finally:
            c.close()

    setup = pika.BlockingConnection(_pika_connect_params())
    try:
        ch = setup.channel()
        ch.exchange_declare(exchange=exchange, exchange_type="topic", durable=True)
        ch.queue_declare(queue=qname, durable=False, exclusive=False, auto_delete=False)
        ch.queue_bind(queue=qname, exchange=exchange, routing_key=routing_key)
    finally:
        setup.close()

    env = os.environ.copy()
    env["RABBITMQ_URL"] = url
    env["MOSCRAPER_DISABLE_PUBLISH"] = "false"
    env["RABBITMQ_EXCHANGE"] = exchange
    env["RABBITMQ_EXCHANGE_TYPE"] = "topic"
    env["RABBITMQ_ROUTING_KEY"] = routing_key
    env["RABBITMQ_PUBLISH_MANDATORY"] = "true"

    try:
        result = subprocess.run(
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
    except subprocess.TimeoutExpired:
        _declare_bind_and_teardown_queue()
        pytest.fail("scrapy crawl mediapark exceeded 240s")

    if result.returncode != 0:
        _declare_bind_and_teardown_queue()
        pytest.skip(
            "mediapark crawl failed (network or site change?). "
            f"stderr tail:\n{result.stderr[-2500:]!s}"
        )

    read = pika.BlockingConnection(_pika_connect_params())
    try:
        rh = read.channel()
        method = None
        body = None
        for _ in range(60):
            method, _properties, body = rh.basic_get(queue=qname, auto_ack=True)
            if method is not None:
                break
            time.sleep(1.0)
        else:
            pytest.fail("no message arrived in bound queue within 60s after crawl")
    finally:
        try:
            ch_del = read.channel()
            ch_del.queue_delete(queue=qname, if_unused=False, if_empty=False)
        except Exception:
            pass
        read.close()

    assert body is not None
    assert isinstance(body, (bytes, bytearray))
    payload = orjson.loads(body)

    event = CloudEventListingScraped.model_validate(payload)
    assert event.specversion == "1.0"
    assert event.type == "com.moscraper.listing.scraped"
    assert event.datacontenttype == "application/json"
    assert event.subject == "listing"
    assert event.data.store == "mediapark"
    assert event.data.entity_key
    assert event.data.url.startswith("http")
