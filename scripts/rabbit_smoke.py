from __future__ import annotations

import argparse
import asyncio
import uuid
from datetime import UTC, datetime

import aio_pika

from config.settings import Settings, settings
from domain.publication_event import PublicationMetadata, ScrapedProductPayload, ScraperProductEvent
from infrastructure.observability import message_codes as obs_mc
from infrastructure.observability.event_logger import log_publisher_event
from scripts.bootstrap_rabbitmq import bootstrap_rabbitmq


def _build_event(cfg: Settings, suffix: str) -> ScraperProductEvent:
    now = datetime.now(UTC)
    event_id = str(uuid.uuid4())
    source_id = f"smoke-{suffix}"
    source_url = f"https://example.invalid/products/{source_id}"
    payload_hash = f"sha256:{uuid.uuid4().hex}"
    return ScraperProductEvent(
        event_id=event_id,
        event_type="scraper.product.scraped.v1",
        schema_version=1,
        store_name="smoke-store",
        source_id=source_id,
        source_url=source_url,
        scrape_run_id=f"rabbit-smoke:{suffix}",
        scraped_at=now,
        payload_hash=payload_hash,
        structured_payload=ScrapedProductPayload(
            store_name="smoke-store",
            source_url=source_url,
            source_id=source_id,
            title="Rabbit Smoke Product",
            brand="SmokeBrand",
            price_raw="100",
            in_stock=True,
            raw_specs={"Mode": "smoke"},
            image_urls=["https://example.invalid/img/smoke.jpg"],
            description="Smoke test event",
            category_hint="smoke",
            external_ids={"smoke-store": source_id},
            scraped_at=now,
            payload_hash=payload_hash,
            raw_payload_snapshot={"title": "Rabbit Smoke Product"},
            scrape_run_id=f"rabbit-smoke:{suffix}",
            identity_key=f"smoke-store:{source_id}",
        ),
        publication=PublicationMetadata(
            publication_version=1,
            exchange_name=cfg.RABBITMQ_EXCHANGE,
            queue_name=cfg.RABBITMQ_QUEUE,
            routing_key=cfg.RABBITMQ_ROUTING_KEY,
            outbox_status="published",
            attempt_number=1,
            publisher_service="rabbit-smoke",
            outbox_created_at=now,
            published_at=now,
        ),
    )


async def _publish_and_read(cfg: Settings, crm_queue: str) -> None:
    publisher_connection = await aio_pika.connect_robust(
        cfg.RABBITMQ_URL,
        heartbeat=cfg.RABBITMQ_HEARTBEAT_SECONDS,
        client_properties={"connection_name": "rabbit-smoke-publisher"},
    )
    crm_connection = await aio_pika.connect_robust(
        cfg.resolved_rabbitmq_crm_url(),
        heartbeat=cfg.RABBITMQ_HEARTBEAT_SECONDS,
        client_properties={"connection_name": "rabbit-smoke-crm"},
    )
    try:
        pub_channel = await publisher_connection.channel(publisher_confirms=True)
        crm_channel = await crm_connection.channel()
        exchange = await pub_channel.get_exchange(cfg.RABBITMQ_EXCHANGE, ensure=False)
        retry_exchange = await crm_channel.get_exchange(cfg.RABBITMQ_RETRY_EXCHANGE, ensure=False)
        queue = await crm_channel.get_queue(crm_queue, ensure=False)
        dlq = await crm_channel.get_queue(f"{crm_queue}.dlq", ensure=False)

        event = _build_event(cfg, "main")
        await exchange.publish(
            aio_pika.Message(
                body=event.model_dump_json(by_alias=True).encode("utf-8"),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=event.event_id,
                type=event.event_type,
            ),
            routing_key=cfg.RABBITMQ_ROUTING_KEY,
            mandatory=True,
        )
        incoming = await queue.get(timeout=10, fail=True)
        parsed = ScraperProductEvent.model_validate_json(incoming.body)
        assert parsed.event_id == event.event_id
        await incoming.ack()

        retry_event = _build_event(cfg, "retry")
        await retry_exchange.publish(
            aio_pika.Message(
                body=retry_event.model_dump_json(by_alias=True).encode("utf-8"),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=retry_event.event_id,
                type=retry_event.event_type,
            ),
            routing_key="30s",
            mandatory=True,
        )
        await asyncio.sleep(max(cfg.RABBITMQ_RETRY_30S_MS / 1000.0 + 2.0, 5.0))
        retried = await queue.get(timeout=10, fail=True)
        retried_event = ScraperProductEvent.model_validate_json(retried.body)
        assert retried_event.event_id == retry_event.event_id
        await retried.ack()

        dlq_event = _build_event(cfg, "dlq")
        await exchange.publish(
            aio_pika.Message(
                body=dlq_event.model_dump_json(by_alias=True).encode("utf-8"),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=dlq_event.event_id,
                type=dlq_event.event_type,
            ),
            routing_key=cfg.RABBITMQ_ROUTING_KEY,
            mandatory=True,
        )
        doomed = await queue.get(timeout=10, fail=True)
        doomed_event = ScraperProductEvent.model_validate_json(doomed.body)
        assert doomed_event.event_id == dlq_event.event_id
        await doomed.reject(requeue=False)
        dead_letter = await dlq.get(timeout=10, fail=True)
        dead_letter_event = ScraperProductEvent.model_validate_json(dead_letter.body)
        assert dead_letter_event.event_id == dlq_event.event_id
        await dead_letter.ack()
    finally:
        await crm_connection.close()
        await publisher_connection.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smoke-test RabbitMQ topology for the scraper -> CRM contour.")
    parser.add_argument("--skip-bootstrap", action="store_true", help="Assume topology already exists.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    cfg = settings
    try:
        if not args.skip_bootstrap:
            bootstrap_rabbitmq(cfg)
        asyncio.run(_publish_and_read(cfg, cfg.RABBITMQ_CRM_QUEUE))
    except Exception as exc:  # noqa: BLE001
        log_publisher_event(
            obs_mc.PUBLISHER_SMOKE_FAILED,
            publisher_service="rabbit-smoke",
            exchange_name=cfg.RABBITMQ_EXCHANGE,
            queue_name=cfg.RABBITMQ_CRM_QUEUE,
            routing_key=cfg.RABBITMQ_ROUTING_KEY,
            severity="error",
            details={
                "error": str(exc),
                "skip_bootstrap": bool(args.skip_bootstrap),
            },
        )
        raise

    log_publisher_event(
        obs_mc.PUBLISHER_SMOKE_COMPLETED,
        publisher_service="rabbit-smoke",
        exchange_name=cfg.RABBITMQ_EXCHANGE,
        queue_name=cfg.RABBITMQ_CRM_QUEUE,
        routing_key=cfg.RABBITMQ_ROUTING_KEY,
        details={
            "retry_exchange": cfg.RABBITMQ_RETRY_EXCHANGE,
            "skip_bootstrap": bool(args.skip_bootstrap),
        },
    )
    print("rabbit_smoke_ok")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
