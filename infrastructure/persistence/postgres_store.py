from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any, Iterator

from psycopg import connect
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from application.ingestion.event_builder import build_scraper_product_event
from config.settings import settings
from domain.publication_event import ScraperProductEvent
from domain.scraped_product import ScrapedProductSnapshot
from infrastructure.persistence.base import ClaimedOutboxMessage, PersistedRawProduct
from infrastructure.persistence.common import flatten_specs, serialize_row, utcnow

_SCHEMA_VERSION = "0002_scraper_postgres_foundation"
_MIGRATION_SQL = Path(__file__).resolve().parents[2] / "shared" / "db" / "migrations" / "0002_scraper_postgres_foundation.sql"


def apply_postgres_schema(dsn: str) -> None:
    sql_text = _MIGRATION_SQL.read_text(encoding="utf-8")
    with connect(dsn, autocommit=True) as connection:
        connection.execute(sql_text)


class PostgresScraperStore:
    def __init__(
        self,
        dsn: str | None = None,
        *,
        auto_prepare: bool = False,
        min_size: int | None = None,
        max_size: int | None = None,
    ) -> None:
        self._dsn = (dsn or settings.SCRAPER_DB_DSN or "").strip()
        if not self._dsn:
            raise ValueError("SCRAPER_DB_DSN must be set when SCRAPER_DB_BACKEND=postgres")
        self._pool = ConnectionPool(
            conninfo=self._dsn,
            min_size=int(min_size or settings.SCRAPER_DB_POOL_MIN_SIZE),
            max_size=int(max_size or settings.SCRAPER_DB_POOL_MAX_SIZE),
            kwargs={"row_factory": dict_row},
            open=True,
        )
        if auto_prepare:
            self.ensure_schema()

    @classmethod
    def from_settings(cls, *, auto_prepare: bool = False) -> "PostgresScraperStore":
        return cls(
            settings.SCRAPER_DB_DSN,
            auto_prepare=auto_prepare,
            min_size=settings.SCRAPER_DB_POOL_MIN_SIZE,
            max_size=settings.SCRAPER_DB_POOL_MAX_SIZE,
        )

    def ensure_schema(self) -> None:
        migration_dsn = (settings.SCRAPER_DB_MIGRATION_DSN or self._dsn).strip()
        apply_postgres_schema(migration_dsn)

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        with self._pool.connection() as connection:
            yield connection

    def register_scrape_run(
        self,
        *,
        scrape_run_id: str,
        store_name: str,
        spider_name: str,
        category_urls: list[str],
    ) -> None:
        now = utcnow()
        with self._connection() as connection, connection.transaction():
            connection.execute(
                """
                insert into scraper.scrape_runs (
                    run_id,
                    store_name,
                    spider_name,
                    started_at,
                    status,
                    items_scraped,
                    items_persisted,
                    items_failed,
                    category_urls_json,
                    stats_json,
                    created_at,
                    updated_at
                )
                values (%s, %s, %s, %s, 'running', 0, 0, 0, %s, %s, %s, %s)
                on conflict (run_id) do update
                   set store_name = excluded.store_name,
                       spider_name = excluded.spider_name,
                       status = 'running',
                       category_urls_json = excluded.category_urls_json,
                       updated_at = excluded.updated_at
                """,
                (
                    scrape_run_id,
                    store_name,
                    spider_name,
                    now,
                    Jsonb(category_urls),
                    Jsonb({}),
                    now,
                    now,
                ),
            )

    def finish_scrape_run(
        self,
        *,
        scrape_run_id: str,
        status: str,
        stats: dict[str, object],
    ) -> None:
        now = utcnow()
        with self._connection() as connection, connection.transaction():
            connection.execute(
                """
                update scraper.scrape_runs
                   set finished_at = %s,
                       status = %s,
                       items_scraped = %s,
                       items_persisted = %s,
                       items_failed = %s,
                       stats_json = %s,
                       updated_at = %s
                 where run_id = %s
                """,
                (
                    now,
                    status,
                    int(stats.get("items_scraped") or stats.get("item_scraped_count") or 0),
                    int(stats.get("items_persisted") or 0),
                    int(stats.get("items_failed") or stats.get("item_dropped_count") or 0),
                    Jsonb(stats),
                    now,
                    scrape_run_id,
                ),
            )

    def persist_snapshot(
        self,
        snapshot: ScrapedProductSnapshot,
        *,
        event_type: str,
        exchange_name: str,
        routing_key: str,
    ) -> PersistedRawProduct:
        now = utcnow()
        event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"outbox:{snapshot.scrape_run_id}:{snapshot.identity_key}"))
        event = build_scraper_product_event(
            snapshot,
            event_id=event_id,
            event_type=event_type,
            exchange_name=exchange_name,
            routing_key=routing_key,
            created_at=now,
        )
        structured_payload = event.structured_payload.model_dump(mode="json")
        payload_json = event.model_dump(mode="json")

        with self._connection() as connection, connection.transaction():
            raw_product_id = self._upsert_raw_product(
                connection,
                snapshot=snapshot,
                structured_payload=structured_payload,
                now=now,
            )
            self._replace_image_rows(
                connection,
                raw_product_id=raw_product_id,
                image_urls=list(snapshot.image_urls),
                now=now,
            )
            self._replace_spec_rows(
                connection,
                raw_product_id=raw_product_id,
                raw_specs=dict(snapshot.raw_specs),
                now=now,
            )
            outbox_id = self._upsert_outbox_row(
                connection,
                raw_product_id=raw_product_id,
                snapshot=snapshot,
                event_id=event_id,
                event_type=event_type,
                exchange_name=exchange_name,
                routing_key=routing_key,
                payload_json=payload_json,
                now=now,
            )
            connection.execute(
                """
                update scraper.raw_products
                   set publication_state = 'pending',
                       updated_at = %s
                 where id = %s
                """,
                (now, raw_product_id),
            )

        return PersistedRawProduct(
            raw_product_id=raw_product_id,
            outbox_id=outbox_id,
            event_id=event_id,
            payload_hash=snapshot.payload_hash,
            publication_state="pending",
        )

    def _upsert_raw_product(
        self,
        connection,
        *,
        snapshot: ScrapedProductSnapshot,
        structured_payload: dict[str, object],
        now,
    ) -> int:
        row = connection.execute(
            """
            insert into scraper.raw_products (
                scrape_run_id,
                store_name,
                source_id,
                source_url,
                identity_key,
                title,
                brand,
                price_raw,
                in_stock,
                description,
                category_hint,
                external_ids_json,
                payload_hash,
                raw_payload_json,
                structured_payload_json,
                scraped_at,
                publication_state,
                created_at,
                updated_at
            )
            values (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s
            )
            on conflict (scrape_run_id, identity_key) do update
               set store_name = excluded.store_name,
                   source_id = excluded.source_id,
                   source_url = excluded.source_url,
                   title = excluded.title,
                   brand = excluded.brand,
                   price_raw = excluded.price_raw,
                   in_stock = excluded.in_stock,
                   description = excluded.description,
                   category_hint = excluded.category_hint,
                   external_ids_json = excluded.external_ids_json,
                   payload_hash = excluded.payload_hash,
                   raw_payload_json = excluded.raw_payload_json,
                   structured_payload_json = excluded.structured_payload_json,
                   scraped_at = excluded.scraped_at,
                   publication_state = 'pending',
                   updated_at = excluded.updated_at
            returning id
            """,
            (
                snapshot.scrape_run_id,
                snapshot.store_name,
                snapshot.source_id,
                snapshot.source_url,
                snapshot.identity_key,
                snapshot.title,
                snapshot.brand,
                snapshot.price_raw,
                snapshot.in_stock,
                snapshot.description,
                snapshot.category_hint,
                Jsonb(snapshot.external_ids),
                snapshot.payload_hash,
                Jsonb(snapshot.raw_payload),
                Jsonb(structured_payload),
                snapshot.scraped_at,
                now,
                now,
            ),
        ).fetchone()
        return int(row["id"])

    def _replace_image_rows(
        self,
        connection,
        *,
        raw_product_id: int,
        image_urls: list[str],
        now,
    ) -> None:
        connection.execute("delete from scraper.raw_product_images where raw_product_id = %s", (raw_product_id,))
        if not image_urls:
            return
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                insert into scraper.raw_product_images (
                    raw_product_id,
                    image_url,
                    position,
                    created_at,
                    updated_at
                )
                values (%s, %s, %s, %s, %s)
                """,
                [(raw_product_id, image_url, position, now, now) for position, image_url in enumerate(image_urls)],
            )

    def _replace_spec_rows(
        self,
        connection,
        *,
        raw_product_id: int,
        raw_specs: dict[str, Any],
        now,
    ) -> None:
        connection.execute("delete from scraper.raw_product_specs where raw_product_id = %s", (raw_product_id,))
        flattened = flatten_specs(raw_specs)
        if not flattened:
            return
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                insert into scraper.raw_product_specs (
                    raw_product_id,
                    spec_name,
                    spec_value,
                    source_section,
                    position,
                    created_at,
                    updated_at
                )
                values (%s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (raw_product_id, spec.spec_name, spec.spec_value, spec.source_section, position, now, now)
                    for position, spec in enumerate(flattened)
                ],
            )

    def _upsert_outbox_row(
        self,
        connection,
        *,
        raw_product_id: int,
        snapshot: ScrapedProductSnapshot,
        event_id: str,
        event_type: str,
        exchange_name: str,
        routing_key: str,
        payload_json: dict[str, object],
        now,
    ) -> int:
        row = connection.execute(
            """
            insert into scraper.publication_outbox (
                raw_product_id,
                event_id,
                event_type,
                schema_version,
                scrape_run_id,
                store_name,
                source_id,
                source_url,
                payload_hash,
                exchange_name,
                routing_key,
                payload_json,
                status,
                available_at,
                published_at,
                retry_count,
                last_error,
                lease_owner,
                lease_expires_at,
                created_at,
                updated_at
            )
            values (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s, null, 0, null, null, null, %s, %s
            )
            on conflict (event_id) do update
               set raw_product_id = excluded.raw_product_id,
                   event_type = excluded.event_type,
                   schema_version = excluded.schema_version,
                   scrape_run_id = excluded.scrape_run_id,
                   store_name = excluded.store_name,
                   source_id = excluded.source_id,
                   source_url = excluded.source_url,
                   payload_hash = excluded.payload_hash,
                   exchange_name = excluded.exchange_name,
                   routing_key = excluded.routing_key,
                   payload_json = excluded.payload_json,
                   status = 'pending',
                   available_at = excluded.available_at,
                   published_at = null,
                   retry_count = 0,
                   last_error = null,
                   lease_owner = null,
                   lease_expires_at = null,
                   updated_at = excluded.updated_at
            returning id
            """,
            (
                raw_product_id,
                event_id,
                event_type,
                int(settings.MESSAGE_SCHEMA_VERSION),
                snapshot.scrape_run_id,
                snapshot.store_name,
                snapshot.source_id,
                snapshot.source_url,
                snapshot.payload_hash,
                exchange_name,
                routing_key,
                Jsonb(payload_json),
                now,
                now,
                now,
            ),
        ).fetchone()
        return int(row["id"])

    def save_snapshot_and_enqueue(
        self,
        snapshot: ScrapedProductSnapshot,
        *,
        event_type: str,
        exchange_name: str,
        routing_key: str,
    ) -> str:
        result = self.persist_snapshot(
            snapshot,
            event_type=event_type,
            exchange_name=exchange_name,
            routing_key=routing_key,
        )
        return result.event_id

    def has_claimable_outbox_rows(self) -> bool:
        now = utcnow()
        with self._connection() as connection:
            row = connection.execute(
                """
                select 1
                  from scraper.publication_outbox
                 where (
                        (status in ('pending', 'retryable') and available_at <= %s)
                     or (status = 'leased' and lease_expires_at is not null and lease_expires_at <= %s)
                 )
                 limit 1
                """,
                (now, now),
            ).fetchone()
        return row is not None

    def claim_outbox_batch(
        self,
        *,
        batch_size: int,
        publisher_id: str,
        lease_seconds: int,
    ) -> list[ClaimedOutboxMessage]:
        now = utcnow()
        lease_expires = now + timedelta(seconds=max(lease_seconds, 1))
        with self._connection() as connection, connection.transaction():
            rows = connection.execute(
                """
                select id
                  from scraper.publication_outbox
                 where (
                        (status in ('pending', 'retryable') and available_at <= %s)
                     or (status = 'leased' and lease_expires_at is not null and lease_expires_at <= %s)
                 )
                 order by created_at asc
                 for update skip locked
                 limit %s
                """,
                (now, now, int(batch_size)),
            ).fetchall()
            outbox_ids = [int(row["id"]) for row in rows]
            if not outbox_ids:
                return []

            claimed_rows = connection.execute(
                """
                update scraper.publication_outbox
                   set status = 'leased',
                       lease_owner = %s,
                       lease_expires_at = %s,
                       updated_at = %s
                 where id = any(%s)
             returning id, raw_product_id, event_id, exchange_name, routing_key, retry_count, payload_json, created_at
                """,
                (publisher_id, lease_expires, now, outbox_ids),
            ).fetchall()
            connection.execute(
                """
                update scraper.raw_products
                   set publication_state = 'leased',
                       updated_at = %s
                 where id = any(%s)
                """,
                (now, [int(row["raw_product_id"]) for row in claimed_rows]),
            )

        claimed_rows = sorted(claimed_rows, key=lambda row: row["created_at"])
        return [
            ClaimedOutboxMessage(
                event_id=str(row["event_id"]),
                exchange_name=str(row["exchange_name"]),
                routing_key=str(row["routing_key"]),
                attempt_count=int(row["retry_count"]),
                payload=ScraperProductEvent.model_validate(row["payload_json"]),
            )
            for row in claimed_rows
        ]

    def mark_outbox_published(
        self,
        *,
        event_id: str,
        publisher_id: str,
        exchange_name: str,
        routing_key: str,
        published_event: ScraperProductEvent | None = None,
    ) -> None:
        del exchange_name, routing_key
        now = published_event.publication.published_at if published_event and published_event.publication.published_at else utcnow()
        payload_json = None if published_event is None else Jsonb(published_event.model_dump(mode="json"))
        with self._connection() as connection, connection.transaction():
            row = connection.execute(
                """
                select id, raw_product_id, retry_count
                  from scraper.publication_outbox
                 where event_id = %s
                 for update
                """,
                (event_id,),
            ).fetchone()
            if row is None:
                return
            outbox_id = int(row["id"])
            attempt_number = int(row["retry_count"]) + 1
            connection.execute(
                """
                update scraper.publication_outbox
                   set status = 'published',
                       retry_count = %s,
                       payload_json = coalesce(%s::jsonb, payload_json),
                       published_at = %s,
                       lease_owner = null,
                       lease_expires_at = null,
                       last_error = null,
                       updated_at = %s
                 where id = %s
                """,
                (attempt_number, payload_json, now, now, outbox_id),
            )
            connection.execute(
                """
                update scraper.raw_products
                   set publication_state = 'published',
                       updated_at = %s
                 where id = %s
                """,
                (now, int(row["raw_product_id"])),
            )
            connection.execute(
                """
                insert into scraper.publication_attempts (
                    outbox_id,
                    attempt_number,
                    attempted_at,
                    success,
                    error_message,
                    publisher_name,
                    created_at
                )
                values (%s, %s, %s, true, null, %s, %s)
                on conflict (outbox_id, attempt_number) do update
                   set success = excluded.success,
                       error_message = excluded.error_message,
                       publisher_name = excluded.publisher_name,
                       created_at = excluded.created_at
                """,
                (outbox_id, attempt_number, now, publisher_id, now),
            )

    def mark_outbox_failed(
        self,
        *,
        event_id: str,
        publisher_id: str,
        exchange_name: str,
        routing_key: str,
        error_message: str,
        retryable: bool,
        max_retries: int | None = None,
        retry_base_seconds: int | None = None,
    ) -> None:
        del exchange_name, routing_key
        now = utcnow()
        with self._connection() as connection, connection.transaction():
            row = connection.execute(
                """
                select id, raw_product_id, retry_count
                  from scraper.publication_outbox
                 where event_id = %s
                 for update
                """,
                (event_id,),
            ).fetchone()
            if row is None:
                return
            outbox_id = int(row["id"])
            attempt_number = int(row["retry_count"]) + 1
            max_retry_count = max(int(max_retries or settings.SCRAPER_OUTBOX_MAX_RETRIES), 1)
            retry_delay_seconds = max(int(retry_base_seconds or settings.SCRAPER_OUTBOX_RETRY_BASE_SECONDS), 1)
            can_retry = retryable and attempt_number < max_retry_count
            next_status = "retryable" if can_retry else "failed"
            backoff_seconds = retry_delay_seconds * max(1, 2 ** max(attempt_number - 1, 0))
            available_at = now + timedelta(seconds=backoff_seconds if can_retry else 0)

            connection.execute(
                """
                update scraper.publication_outbox
                   set status = %s,
                       retry_count = %s,
                       available_at = %s,
                       lease_owner = null,
                       lease_expires_at = null,
                       last_error = %s,
                       updated_at = %s
                 where id = %s
                """,
                (next_status, attempt_number, available_at, error_message, now, outbox_id),
            )
            connection.execute(
                """
                update scraper.raw_products
                   set publication_state = %s,
                       updated_at = %s
                 where id = %s
                """,
                (next_status, now, int(row["raw_product_id"])),
            )
            connection.execute(
                """
                insert into scraper.publication_attempts (
                    outbox_id,
                    attempt_number,
                    attempted_at,
                    success,
                    error_message,
                    publisher_name,
                    created_at
                )
                values (%s, %s, %s, false, %s, %s, %s)
                on conflict (outbox_id, attempt_number) do update
                   set success = excluded.success,
                       error_message = excluded.error_message,
                       publisher_name = excluded.publisher_name,
                       created_at = excluded.created_at
                """,
                (outbox_id, attempt_number, now, error_message, publisher_id, now),
            )

    def get_scrape_run_row(self, run_id: str) -> dict[str, object] | None:
        with self._connection() as connection:
            row = connection.execute(
                "select * from scraper.scrape_runs where run_id = %s",
                (run_id,),
            ).fetchone()
        return None if row is None else serialize_row(dict(row))

    def get_snapshot_row(self, *, scrape_run_id: str, identity_key: str) -> dict[str, object] | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                select *
                  from scraper.raw_products
                 where scrape_run_id = %s
                   and identity_key = %s
                """,
                (scrape_run_id, identity_key),
            ).fetchone()
        return None if row is None else serialize_row(dict(row))

    def get_raw_product_images(self, raw_product_id: int) -> list[dict[str, object]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                select *
                  from scraper.raw_product_images
                 where raw_product_id = %s
                 order by position asc
                """,
                (raw_product_id,),
            ).fetchall()
        return [serialize_row(dict(row)) for row in rows]

    def get_raw_product_specs(self, raw_product_id: int) -> list[dict[str, object]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                select *
                  from scraper.raw_product_specs
                 where raw_product_id = %s
                 order by position asc
                """,
                (raw_product_id,),
            ).fetchall()
        return [serialize_row(dict(row)) for row in rows]

    def get_outbox_row(self, event_id: str) -> dict[str, object] | None:
        with self._connection() as connection:
            row = connection.execute(
                "select * from scraper.publication_outbox where event_id = %s",
                (event_id,),
            ).fetchone()
        return None if row is None else serialize_row(dict(row))

    def get_publication_attempts(self, outbox_id: int) -> list[dict[str, object]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                select *
                  from scraper.publication_attempts
                 where outbox_id = %s
                 order by attempt_number asc
                """,
                (outbox_id,),
            ).fetchall()
        return [serialize_row(dict(row)) for row in rows]

    def close(self) -> None:
        self._pool.close()


__all__ = ["PostgresScraperStore", "apply_postgres_schema", "_SCHEMA_VERSION"]
