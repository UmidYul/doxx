from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

import orjson

from application.ingestion.event_builder import build_scraper_product_event
from config.settings import settings
from domain.publication_event import ScraperProductEvent
from domain.scrape_fingerprints import normalize_text
from domain.scraped_product import ScrapedProductSnapshot

_FOUNDATION_MIGRATION_VERSION = "0001_scraper_persistence_foundation"
_LEGACY_SCRAPE_RUNS = "scrape_runs_legacy_v0"
_LEGACY_SCRAPED_PRODUCTS = "scraped_products_legacy_v0"
_LEGACY_PUBLICATION_OUTBOX = "publication_outbox_legacy_v0"
_LEGACY_PUBLICATION_ATTEMPTS = "publication_attempts_legacy_v0"

_SCHEMA_STATEMENTS = (
    """
    create table if not exists schema_migrations (
        version text primary key,
        applied_at text not null
    )
    """,
    """
    create table if not exists scrape_runs (
        id integer primary key autoincrement,
        run_id text not null unique,
        store_name text not null,
        spider_name text not null,
        started_at text not null,
        finished_at text,
        status text not null,
        items_scraped integer not null default 0,
        items_persisted integer not null default 0,
        items_failed integer not null default 0,
        category_urls_json text not null default '[]',
        stats_json text not null default '{}',
        created_at text not null,
        updated_at text not null
    )
    """,
    "create index if not exists ix_scrape_runs_store_started_at on scrape_runs(store_name, started_at desc)",
    "create index if not exists ix_scrape_runs_status on scrape_runs(status, started_at desc)",
    """
    create table if not exists raw_products (
        id integer primary key autoincrement,
        scrape_run_id text not null references scrape_runs(run_id) on delete cascade,
        store_name text not null,
        source_id text,
        source_url text not null,
        identity_key text not null,
        title text not null,
        brand text,
        price_raw text,
        in_stock integer,
        description text,
        category_hint text,
        external_ids_json text not null default '{}',
        payload_hash text not null,
        raw_payload_json text not null default '{}',
        structured_payload_json text not null default '{}',
        scraped_at text not null,
        publication_state text not null default 'pending',
        created_at text not null,
        updated_at text not null,
        unique(scrape_run_id, identity_key)
    )
    """,
    "create index if not exists ix_raw_products_store_name on raw_products(store_name, scraped_at desc)",
    "create index if not exists ix_raw_products_scrape_run_id on raw_products(scrape_run_id, scraped_at desc)",
    "create index if not exists ix_raw_products_store_source_id on raw_products(store_name, source_id)",
    "create index if not exists ix_raw_products_store_source_url on raw_products(store_name, source_url)",
    "create index if not exists ix_raw_products_publication_state on raw_products(publication_state, scraped_at desc)",
    "create index if not exists ix_raw_products_payload_hash on raw_products(payload_hash)",
    """
    create table if not exists raw_product_images (
        id integer primary key autoincrement,
        raw_product_id integer not null references raw_products(id) on delete cascade,
        image_url text not null,
        position integer not null,
        created_at text not null,
        updated_at text not null,
        unique(raw_product_id, image_url),
        unique(raw_product_id, position)
    )
    """,
    "create index if not exists ix_raw_product_images_product_position on raw_product_images(raw_product_id, position asc)",
    """
    create table if not exists raw_product_specs (
        id integer primary key autoincrement,
        raw_product_id integer not null references raw_products(id) on delete cascade,
        spec_name text not null,
        spec_value text not null,
        source_section text,
        position integer not null,
        created_at text not null,
        updated_at text not null,
        unique(raw_product_id, position)
    )
    """,
    "create index if not exists ix_raw_product_specs_product_position on raw_product_specs(raw_product_id, position asc)",
    "create index if not exists ix_raw_product_specs_name on raw_product_specs(spec_name)",
    "create unique index if not exists ux_raw_product_specs_identity on raw_product_specs(raw_product_id, spec_name, spec_value, ifnull(source_section, ''))",
    """
    create table if not exists publication_outbox (
        id integer primary key autoincrement,
        raw_product_id integer not null unique references raw_products(id) on delete cascade,
        event_id text not null unique,
        event_type text not null,
        schema_version integer not null,
        scrape_run_id text not null references scrape_runs(run_id) on delete cascade,
        store_name text not null,
        source_id text,
        source_url text not null,
        payload_hash text not null,
        exchange_name text not null,
        routing_key text not null,
        payload_json text not null,
        status text not null,
        available_at text not null,
        published_at text,
        retry_count integer not null default 0,
        last_error text,
        lease_owner text,
        lease_expires_at text,
        created_at text not null,
        updated_at text not null
    )
    """,
    "create index if not exists ix_publication_outbox_status_available on publication_outbox(status, available_at asc)",
    "create index if not exists ix_publication_outbox_store_status on publication_outbox(store_name, status, created_at asc)",
    "create index if not exists ix_publication_outbox_scrape_run on publication_outbox(scrape_run_id, created_at asc)",
    "create index if not exists ix_publication_outbox_payload_hash on publication_outbox(payload_hash)",
    """
    create table if not exists publication_attempts (
        id integer primary key autoincrement,
        outbox_id integer not null references publication_outbox(id) on delete cascade,
        attempt_number integer not null,
        attempted_at text not null,
        success integer not null,
        error_message text,
        publisher_name text,
        created_at text not null,
        unique(outbox_id, attempt_number)
    )
    """,
    "create index if not exists ix_publication_attempts_outbox_attempted_at on publication_attempts(outbox_id, attempted_at desc)",
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat().replace("+00:00", "Z")


def _json_dumps(payload: object) -> str:
    return orjson.dumps(payload).decode("utf-8")


def _json_loads(payload: str) -> object:
    return orjson.loads(payload)


@dataclass(slots=True)
class ClaimedOutboxMessage:
    event_id: str
    exchange_name: str
    routing_key: str
    attempt_count: int
    payload: ScraperProductEvent


@dataclass(slots=True)
class PersistedRawProduct:
    raw_product_id: int
    outbox_id: int
    event_id: str
    payload_hash: str
    publication_state: str


@dataclass(slots=True)
class _FlattenedSpec:
    spec_name: str
    spec_value: str
    source_section: str | None = None


class SQLiteScraperStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path or settings.SCRAPER_DB_PATH)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_schema()

    @classmethod
    def from_settings(cls) -> "SQLiteScraperStore":
        return cls(settings.SCRAPER_DB_PATH)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            str(self._db_path),
            timeout=max(float(settings.SCRAPER_DB_BUSY_TIMEOUT_MS) / 1000.0, 0.1),
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("pragma foreign_keys = on")
        connection.execute(f"pragma busy_timeout = {int(settings.SCRAPER_DB_BUSY_TIMEOUT_MS)}")
        if settings.SCRAPER_DB_ENABLE_WAL:
            connection.execute("pragma journal_mode = wal")
            connection.execute("pragma synchronous = normal")
        return connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("begin immediate")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def ensure_schema(self) -> None:
        with self._transaction() as connection:
            connection.execute(
                """
                create table if not exists schema_migrations (
                    version text primary key,
                    applied_at text not null
                )
                """
            )
            applied = connection.execute(
                "select 1 from schema_migrations where version = ?",
                (_FOUNDATION_MIGRATION_VERSION,),
            ).fetchone()
            if applied is None:
                self._prepare_legacy_tables(connection)
            for statement in _SCHEMA_STATEMENTS:
                connection.execute(statement)
            if applied is None:
                self._migrate_legacy_data(connection)
                connection.execute(
                    "insert into schema_migrations(version, applied_at) values (?, ?)",
                    (_FOUNDATION_MIGRATION_VERSION, _iso(_utcnow())),
                )

    def _prepare_legacy_tables(self, connection: sqlite3.Connection) -> None:
        self._rename_legacy_table(
            connection,
            current_name="scrape_runs",
            legacy_name=_LEGACY_SCRAPE_RUNS,
            when_missing_columns=("run_id", "items_scraped", "items_persisted", "items_failed"),
        )
        self._rename_legacy_table(
            connection,
            current_name="scraped_products",
            legacy_name=_LEGACY_SCRAPED_PRODUCTS,
            when_missing_columns=(),
        )
        self._rename_legacy_table(
            connection,
            current_name="publication_outbox",
            legacy_name=_LEGACY_PUBLICATION_OUTBOX,
            when_missing_columns=("id", "raw_product_id", "schema_version", "retry_count"),
        )
        self._rename_legacy_table(
            connection,
            current_name="publication_attempts",
            legacy_name=_LEGACY_PUBLICATION_ATTEMPTS,
            when_missing_columns=("id", "outbox_id", "success"),
        )

    def _rename_legacy_table(
        self,
        connection: sqlite3.Connection,
        *,
        current_name: str,
        legacy_name: str,
        when_missing_columns: tuple[str, ...],
    ) -> None:
        if not self._table_exists(connection, current_name):
            return
        if self._table_exists(connection, legacy_name):
            return
        if when_missing_columns and all(self._table_has_column(connection, current_name, column) for column in when_missing_columns):
            return
        connection.execute(f"alter table {current_name} rename to {legacy_name}")

    def _migrate_legacy_data(self, connection: sqlite3.Connection) -> None:
        self._migrate_legacy_scrape_runs(connection)
        item_mapping = self._migrate_legacy_scraped_products(connection)
        self._migrate_legacy_outbox(connection, item_mapping)
        self._migrate_legacy_attempts(connection)

    def _migrate_legacy_scrape_runs(self, connection: sqlite3.Connection) -> None:
        if not self._table_exists(connection, _LEGACY_SCRAPE_RUNS):
            return
        rows = connection.execute(f"select * from {_LEGACY_SCRAPE_RUNS}").fetchall()
        for row in rows:
            stats = self._safe_json_dict(row["stats_json"])
            started_at = str(row["started_at"])
            created_at = str(row["created_at"]) if "created_at" in row.keys() else started_at
            updated_at = str(row["updated_at"]) if "updated_at" in row.keys() else created_at
            connection.execute(
                """
                insert into scrape_runs (
                    run_id,
                    store_name,
                    spider_name,
                    started_at,
                    finished_at,
                    status,
                    items_scraped,
                    items_persisted,
                    items_failed,
                    category_urls_json,
                    stats_json,
                    created_at,
                    updated_at
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(run_id) do update set
                    store_name = excluded.store_name,
                    spider_name = excluded.spider_name,
                    finished_at = excluded.finished_at,
                    status = excluded.status,
                    items_scraped = excluded.items_scraped,
                    items_persisted = excluded.items_persisted,
                    items_failed = excluded.items_failed,
                    category_urls_json = excluded.category_urls_json,
                    stats_json = excluded.stats_json,
                    updated_at = excluded.updated_at
                """,
                (
                    str(row["scrape_run_id"]),
                    str(row["store_name"]),
                    str(row["spider_name"]),
                    started_at,
                    None if row["finished_at"] is None else str(row["finished_at"]),
                    str(row["status"]),
                    int(stats.get("items_scraped") or stats.get("item_scraped_count") or 0),
                    int(stats.get("items_persisted") or 0),
                    int(stats.get("items_failed") or stats.get("item_dropped_count") or 0),
                    str(row["category_urls_json"]) if "category_urls_json" in row.keys() else "[]",
                    str(row["stats_json"]) if "stats_json" in row.keys() else "{}",
                    created_at,
                    updated_at,
                ),
            )

    def _migrate_legacy_scraped_products(self, connection: sqlite3.Connection) -> dict[str, int]:
        item_mapping: dict[str, int] = {}
        if not self._table_exists(connection, _LEGACY_SCRAPED_PRODUCTS):
            return item_mapping

        rows = connection.execute(f"select * from {_LEGACY_SCRAPED_PRODUCTS} order by created_at asc").fetchall()
        for row in rows:
            scrape_run_id = str(row["scrape_run_id"])
            structured_payload = {
                "store_name": str(row["store_name"]),
                "source_url": str(row["source_url"]),
                "source_id": None if row["source_id"] is None else str(row["source_id"]),
                "title": str(row["title"]),
                "brand": None if row["brand"] is None else str(row["brand"]),
                "price_raw": None if row["price_raw"] is None else str(row["price_raw"]),
                "in_stock": None if row["in_stock"] is None else bool(row["in_stock"]),
                "raw_specs": self._safe_json_dict(row["raw_specs_json"]),
                "image_urls": self._safe_json_list(row["image_urls_json"]),
                "description": None if row["description"] is None else str(row["description"]),
                "category_hint": None if row["category_hint"] is None else str(row["category_hint"]),
                "external_ids": self._safe_json_dict(row["external_ids_json"]),
                "scraped_at": str(row["scraped_at"]),
                "payload_hash": str(row["payload_hash"]),
                "raw_payload_snapshot": self._safe_json_dict(row["raw_payload_json"]),
                "scrape_run_id": scrape_run_id,
                "identity_key": str(row["identity_key"]),
            }
            connection.execute(
                """
                insert into raw_products (
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
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                on conflict(scrape_run_id, identity_key) do update set
                    store_name = excluded.store_name,
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
                    updated_at = excluded.updated_at
                """,
                (
                    scrape_run_id,
                    str(row["store_name"]),
                    None if row["source_id"] is None else str(row["source_id"]),
                    str(row["source_url"]),
                    str(row["identity_key"]),
                    str(row["title"]),
                    None if row["brand"] is None else str(row["brand"]),
                    None if row["price_raw"] is None else str(row["price_raw"]),
                    None if row["in_stock"] is None else int(row["in_stock"]),
                    None if row["description"] is None else str(row["description"]),
                    None if row["category_hint"] is None else str(row["category_hint"]),
                    str(row["external_ids_json"]),
                    str(row["payload_hash"]),
                    str(row["raw_payload_json"]),
                    _json_dumps(structured_payload),
                    str(row["scraped_at"]),
                    str(row["created_at"]),
                    str(row["updated_at"]),
                ),
            )
            product_row = connection.execute(
                """
                select id
                  from raw_products
                 where scrape_run_id = ?
                   and identity_key = ?
                """,
                (scrape_run_id, str(row["identity_key"])),
            ).fetchone()
            if product_row is None:
                continue
            raw_product_id = int(product_row["id"])
            item_mapping[str(row["item_id"])] = raw_product_id
            self._replace_image_rows(
                connection,
                raw_product_id=raw_product_id,
                image_urls=self._safe_json_list(row["image_urls_json"]),
                now=str(row["updated_at"]),
            )
            self._replace_spec_rows(
                connection,
                raw_product_id=raw_product_id,
                raw_specs=self._safe_json_dict(row["raw_specs_json"]),
                now=str(row["updated_at"]),
            )
        return item_mapping

    def _migrate_legacy_outbox(self, connection: sqlite3.Connection, item_mapping: dict[str, int]) -> None:
        if not self._table_exists(connection, _LEGACY_PUBLICATION_OUTBOX):
            return
        rows = connection.execute(f"select * from {_LEGACY_PUBLICATION_OUTBOX} order by created_at asc").fetchall()
        for row in rows:
            raw_product_id = item_mapping.get(str(row["item_id"]))
            if raw_product_id is None:
                continue
            payload_json = str(row["payload_json"])
            connection.execute(
                """
                insert into publication_outbox (
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
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(event_id) do update set
                    raw_product_id = excluded.raw_product_id,
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
                    status = excluded.status,
                    available_at = excluded.available_at,
                    published_at = excluded.published_at,
                    retry_count = excluded.retry_count,
                    last_error = excluded.last_error,
                    lease_owner = excluded.lease_owner,
                    lease_expires_at = excluded.lease_expires_at,
                    updated_at = excluded.updated_at
                """,
                (
                    raw_product_id,
                    str(row["event_id"]),
                    str(row["event_type"]),
                    self._extract_schema_version(payload_json),
                    str(row["scrape_run_id"]),
                    str(row["store_name"]),
                    None if row["source_id"] is None else str(row["source_id"]),
                    str(row["source_url"]),
                    str(row["payload_hash"]),
                    str(row["exchange_name"]),
                    str(row["routing_key"]),
                    payload_json,
                    str(row["status"]),
                    str(row["available_at"]),
                    None if row["published_at"] is None else str(row["published_at"]),
                    int(row["attempt_count"]),
                    None if row["last_error"] is None else str(row["last_error"]),
                    None if row["leased_by"] is None else str(row["leased_by"]),
                    None if row["lease_expires_at"] is None else str(row["lease_expires_at"]),
                    str(row["created_at"]),
                    str(row["updated_at"]),
                ),
            )
            connection.execute(
                "update raw_products set publication_state = ? where id = ?",
                (str(row["status"]), raw_product_id),
            )

    def _migrate_legacy_attempts(self, connection: sqlite3.Connection) -> None:
        if not self._table_exists(connection, _LEGACY_PUBLICATION_ATTEMPTS):
            return
        rows = connection.execute(f"select * from {_LEGACY_PUBLICATION_ATTEMPTS} order by created_at asc").fetchall()
        for row in rows:
            outbox_row = connection.execute(
                "select id from publication_outbox where event_id = ?",
                (str(row["event_id"]),),
            ).fetchone()
            if outbox_row is None:
                continue
            connection.execute(
                """
                insert into publication_attempts (
                    outbox_id,
                    attempt_number,
                    attempted_at,
                    success,
                    error_message,
                    publisher_name,
                    created_at
                )
                values (?, ?, ?, ?, ?, ?, ?)
                on conflict(outbox_id, attempt_number) do nothing
                """,
                (
                    int(outbox_row["id"]),
                    int(row["attempt_number"]),
                    str(row["attempted_at"]),
                    1 if str(row["status"]) == "published" else 0,
                    None if row["error_message"] is None else str(row["error_message"]),
                    None if row["publisher_id"] is None else str(row["publisher_id"]),
                    str(row["created_at"]),
                ),
            )

    def register_scrape_run(
        self,
        *,
        scrape_run_id: str,
        store_name: str,
        spider_name: str,
        category_urls: list[str],
    ) -> None:
        now = _utcnow()
        with self._transaction() as connection:
            connection.execute(
                """
                insert into scrape_runs (
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
                values (?, ?, ?, ?, 'running', 0, 0, 0, ?, '{}', ?, ?)
                on conflict(run_id) do update set
                    store_name = excluded.store_name,
                    spider_name = excluded.spider_name,
                    status = 'running',
                    category_urls_json = excluded.category_urls_json,
                    updated_at = excluded.updated_at
                """,
                (
                    scrape_run_id,
                    store_name,
                    spider_name,
                    _iso(now),
                    _json_dumps(category_urls),
                    _iso(now),
                    _iso(now),
                ),
            )

    def finish_scrape_run(
        self,
        *,
        scrape_run_id: str,
        status: str,
        stats: dict[str, object],
    ) -> None:
        now = _utcnow()
        with self._transaction() as connection:
            connection.execute(
                """
                update scrape_runs
                   set finished_at = ?,
                       status = ?,
                       items_scraped = ?,
                       items_persisted = ?,
                       items_failed = ?,
                       stats_json = ?,
                       updated_at = ?
                 where run_id = ?
                """,
                (
                    _iso(now),
                    status,
                    int(stats.get("items_scraped") or stats.get("item_scraped_count") or 0),
                    int(stats.get("items_persisted") or 0),
                    int(stats.get("items_failed") or stats.get("item_dropped_count") or 0),
                    _json_dumps(stats),
                    _iso(now),
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
        now = _utcnow()
        event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"outbox:{snapshot.scrape_run_id}:{snapshot.identity_key}"))
        event = build_scraper_product_event(
            snapshot,
            event_id=event_id,
            event_type=event_type,
            exchange_name=exchange_name,
            routing_key=routing_key,
            created_at=now,
        )
        structured_payload_json = _json_dumps(event.structured_payload.model_dump(mode="json"))
        payload_json = _json_dumps(event.model_dump(mode="json"))

        with self._transaction() as connection:
            raw_product_id = self._upsert_raw_product(
                connection,
                snapshot=snapshot,
                structured_payload_json=structured_payload_json,
                now=now,
            )
            self._replace_image_rows(
                connection,
                raw_product_id=raw_product_id,
                image_urls=list(snapshot.image_urls),
                now=_iso(now),
            )
            self._replace_spec_rows(
                connection,
                raw_product_id=raw_product_id,
                raw_specs=dict(snapshot.raw_specs),
                now=_iso(now),
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
                "update raw_products set publication_state = 'pending', updated_at = ? where id = ?",
                (_iso(now), raw_product_id),
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
        connection: sqlite3.Connection,
        *,
        snapshot: ScrapedProductSnapshot,
        structured_payload_json: str,
        now: datetime,
    ) -> int:
        existing = connection.execute(
            """
            select id
              from raw_products
             where scrape_run_id = ?
               and identity_key = ?
            """,
            (snapshot.scrape_run_id, snapshot.identity_key),
        ).fetchone()
        now_iso = _iso(now)
        if existing is None:
            cursor = connection.execute(
                """
                insert into raw_products (
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
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
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
                    None if snapshot.in_stock is None else int(snapshot.in_stock),
                    snapshot.description,
                    snapshot.category_hint,
                    _json_dumps(snapshot.external_ids),
                    snapshot.payload_hash,
                    _json_dumps(snapshot.raw_payload),
                    structured_payload_json,
                    _iso(snapshot.scraped_at),
                    now_iso,
                    now_iso,
                ),
            )
            return int(cursor.lastrowid)

        raw_product_id = int(existing["id"])
        connection.execute(
            """
            update raw_products
               set store_name = ?,
                   source_id = ?,
                   source_url = ?,
                   title = ?,
                   brand = ?,
                   price_raw = ?,
                   in_stock = ?,
                   description = ?,
                   category_hint = ?,
                   external_ids_json = ?,
                   payload_hash = ?,
                   raw_payload_json = ?,
                   structured_payload_json = ?,
                   scraped_at = ?,
                   publication_state = 'pending',
                   updated_at = ?
             where id = ?
            """,
            (
                snapshot.store_name,
                snapshot.source_id,
                snapshot.source_url,
                snapshot.title,
                snapshot.brand,
                snapshot.price_raw,
                None if snapshot.in_stock is None else int(snapshot.in_stock),
                snapshot.description,
                snapshot.category_hint,
                _json_dumps(snapshot.external_ids),
                snapshot.payload_hash,
                _json_dumps(snapshot.raw_payload),
                structured_payload_json,
                _iso(snapshot.scraped_at),
                now_iso,
                raw_product_id,
            ),
        )
        return raw_product_id

    def _replace_image_rows(
        self,
        connection: sqlite3.Connection,
        *,
        raw_product_id: int,
        image_urls: list[str],
        now: str,
    ) -> None:
        connection.execute("delete from raw_product_images where raw_product_id = ?", (raw_product_id,))
        for position, image_url in enumerate(image_urls):
            connection.execute(
                """
                insert into raw_product_images (
                    raw_product_id,
                    image_url,
                    position,
                    created_at,
                    updated_at
                )
                values (?, ?, ?, ?, ?)
                """,
                (raw_product_id, image_url, position, now, now),
            )

    def _replace_spec_rows(
        self,
        connection: sqlite3.Connection,
        *,
        raw_product_id: int,
        raw_specs: dict[str, Any],
        now: str,
    ) -> None:
        connection.execute("delete from raw_product_specs where raw_product_id = ?", (raw_product_id,))
        for position, spec in enumerate(self._flatten_specs(raw_specs)):
            connection.execute(
                """
                insert into raw_product_specs (
                    raw_product_id,
                    spec_name,
                    spec_value,
                    source_section,
                    position,
                    created_at,
                    updated_at
                )
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                (raw_product_id, spec.spec_name, spec.spec_value, spec.source_section, position, now, now),
            )

    def _upsert_outbox_row(
        self,
        connection: sqlite3.Connection,
        *,
        raw_product_id: int,
        snapshot: ScrapedProductSnapshot,
        event_id: str,
        event_type: str,
        exchange_name: str,
        routing_key: str,
        payload_json: str,
        now: datetime,
    ) -> int:
        existing = connection.execute(
            "select id from publication_outbox where event_id = ?",
            (event_id,),
        ).fetchone()
        now_iso = _iso(now)
        if existing is None:
            cursor = connection.execute(
                """
                insert into publication_outbox (
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
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, null, 0, null, null, null, ?, ?)
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
                    payload_json,
                    now_iso,
                    now_iso,
                    now_iso,
                ),
            )
            return int(cursor.lastrowid)

        outbox_id = int(existing["id"])
        connection.execute(
            """
            update publication_outbox
               set raw_product_id = ?,
                   event_type = ?,
                   schema_version = ?,
                   scrape_run_id = ?,
                   store_name = ?,
                   source_id = ?,
                   source_url = ?,
                   payload_hash = ?,
                   exchange_name = ?,
                   routing_key = ?,
                   payload_json = ?,
                   status = 'pending',
                   available_at = ?,
                   published_at = null,
                   retry_count = 0,
                   last_error = null,
                   lease_owner = null,
                   lease_expires_at = null,
                   updated_at = ?
             where id = ?
            """,
            (
                raw_product_id,
                event_type,
                int(settings.MESSAGE_SCHEMA_VERSION),
                snapshot.scrape_run_id,
                snapshot.store_name,
                snapshot.source_id,
                snapshot.source_url,
                snapshot.payload_hash,
                exchange_name,
                routing_key,
                payload_json,
                now_iso,
                now_iso,
                outbox_id,
            ),
        )
        return outbox_id

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
        """Return whether at least one outbox row is ready to be claimed."""
        now = _utcnow()
        with self._connect() as connection:
            row = connection.execute(
                """
                select 1
                  from publication_outbox
                 where status in ('pending', 'retryable')
                   and available_at <= ?
                   and (lease_expires_at is null or lease_expires_at <= ?)
                 limit 1
                """,
                (_iso(now), _iso(now)),
            ).fetchone()
        return row is not None

    def claim_outbox_batch(
        self,
        *,
        batch_size: int,
        publisher_id: str,
        lease_seconds: int,
    ) -> list[ClaimedOutboxMessage]:
        now = _utcnow()
        lease_expires = now + timedelta(seconds=max(lease_seconds, 1))
        with self._transaction() as connection:
            rows = connection.execute(
                """
                select id
                  from publication_outbox
                 where status in ('pending', 'retryable')
                   and available_at <= ?
                   and (lease_expires_at is null or lease_expires_at <= ?)
                 order by created_at asc
                 limit ?
                """,
                (_iso(now), _iso(now), int(batch_size)),
            ).fetchall()
            outbox_ids = [int(row["id"]) for row in rows]
            if not outbox_ids:
                return []

            placeholders = ", ".join("?" for _ in outbox_ids)
            connection.execute(
                f"""
                update publication_outbox
                   set status = 'publishing',
                       lease_owner = ?,
                       lease_expires_at = ?,
                       updated_at = ?
                 where id in ({placeholders})
                """,
                (publisher_id, _iso(lease_expires), _iso(now), *outbox_ids),
            )
            connection.execute(
                f"""
                update raw_products
                   set publication_state = 'publishing',
                       updated_at = ?
                 where id in (
                    select raw_product_id
                      from publication_outbox
                     where id in ({placeholders})
                 )
                """,
                (_iso(now), *outbox_ids),
            )
            claimed_rows = connection.execute(
                f"""
                select event_id, exchange_name, routing_key, retry_count, payload_json
                  from publication_outbox
                 where id in ({placeholders})
                 order by created_at asc
                """,
                tuple(outbox_ids),
            ).fetchall()

        return [
            ClaimedOutboxMessage(
                event_id=str(row["event_id"]),
                exchange_name=str(row["exchange_name"]),
                routing_key=str(row["routing_key"]),
                attempt_count=int(row["retry_count"]),
                payload=ScraperProductEvent.model_validate(_json_loads(str(row["payload_json"]))),
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
        if published_event is not None and published_event.publication.published_at is not None:
            now = published_event.publication.published_at
            payload_json = _json_dumps(published_event.model_dump(mode="json"))
        else:
            now = _utcnow()
            payload_json = None
        with self._transaction() as connection:
            row = connection.execute(
                "select id, raw_product_id, retry_count from publication_outbox where event_id = ?",
                (event_id,),
            ).fetchone()
            if row is None:
                return
            outbox_id = int(row["id"])
            attempt_number = int(row["retry_count"]) + 1
            connection.execute(
                """
                update publication_outbox
                   set status = 'published',
                       retry_count = ?,
                       payload_json = coalesce(?, payload_json),
                       published_at = ?,
                       lease_owner = null,
                       lease_expires_at = null,
                       last_error = null,
                       updated_at = ?
                 where id = ?
                """,
                (attempt_number, payload_json, _iso(now), _iso(now), outbox_id),
            )
            connection.execute(
                """
                update raw_products
                   set publication_state = 'published',
                       updated_at = ?
                 where id = ?
                """,
                (_iso(now), int(row["raw_product_id"])),
            )
            connection.execute(
                """
                insert into publication_attempts (
                    outbox_id,
                    attempt_number,
                    attempted_at,
                    success,
                    error_message,
                    publisher_name,
                    created_at
                )
                values (?, ?, ?, 1, null, ?, ?)
                on conflict(outbox_id, attempt_number) do update set
                    success = excluded.success,
                    error_message = excluded.error_message,
                    publisher_name = excluded.publisher_name,
                    created_at = excluded.created_at
                """,
                (outbox_id, attempt_number, _iso(now), publisher_id, _iso(now)),
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
        now = _utcnow()
        with self._transaction() as connection:
            row = connection.execute(
                "select id, raw_product_id, retry_count from publication_outbox where event_id = ?",
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
                update publication_outbox
                   set status = ?,
                       retry_count = ?,
                       available_at = ?,
                       lease_owner = null,
                       lease_expires_at = null,
                       last_error = ?,
                       updated_at = ?
                 where id = ?
                """,
                (next_status, attempt_number, _iso(available_at), error_message, _iso(now), outbox_id),
            )
            connection.execute(
                """
                update raw_products
                   set publication_state = ?,
                       updated_at = ?
                 where id = ?
                """,
                (next_status, _iso(now), int(row["raw_product_id"])),
            )
            connection.execute(
                """
                insert into publication_attempts (
                    outbox_id,
                    attempt_number,
                    attempted_at,
                    success,
                    error_message,
                    publisher_name,
                    created_at
                )
                values (?, ?, ?, 0, ?, ?, ?)
                on conflict(outbox_id, attempt_number) do update set
                    success = excluded.success,
                    error_message = excluded.error_message,
                    publisher_name = excluded.publisher_name,
                    created_at = excluded.created_at
                """,
                (outbox_id, attempt_number, _iso(now), error_message, publisher_id, _iso(now)),
            )

    def get_scrape_run_row(self, run_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                "select * from scrape_runs where run_id = ?",
                (run_id,),
            ).fetchone()
            return None if row is None else dict(row)

    def get_snapshot_row(self, *, scrape_run_id: str, identity_key: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                select *
                  from raw_products
                 where scrape_run_id = ?
                   and identity_key = ?
                """,
                (scrape_run_id, identity_key),
            ).fetchone()
            return None if row is None else dict(row)

    def get_raw_product_images(self, raw_product_id: int) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                select *
                  from raw_product_images
                 where raw_product_id = ?
                 order by position asc
                """,
                (raw_product_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_raw_product_specs(self, raw_product_id: int) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                select *
                  from raw_product_specs
                 where raw_product_id = ?
                 order by position asc
                """,
                (raw_product_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_outbox_row(self, event_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                "select * from publication_outbox where event_id = ?",
                (event_id,),
            ).fetchone()
            return None if row is None else dict(row)

    def get_publication_attempts(self, outbox_id: int) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                select *
                  from publication_attempts
                 where outbox_id = ?
                 order by attempt_number asc
                """,
                (outbox_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def close(self) -> None:
        return None

    def _table_exists(self, connection: sqlite3.Connection, table_name: str) -> bool:
        row = connection.execute(
            "select 1 from sqlite_master where type = 'table' and name = ?",
            (table_name,),
        ).fetchone()
        return row is not None

    def _table_has_column(self, connection: sqlite3.Connection, table_name: str, column_name: str) -> bool:
        rows = connection.execute(f"pragma table_info({table_name})").fetchall()
        return any(str(row["name"]) == column_name for row in rows)

    def _safe_json_dict(self, payload: object) -> dict[str, Any]:
        if payload is None:
            return {}
        if isinstance(payload, str):
            try:
                loaded = _json_loads(payload)
            except orjson.JSONDecodeError:
                return {}
            return loaded if isinstance(loaded, dict) else {}
        if isinstance(payload, dict):
            return dict(payload)
        return {}

    def _safe_json_list(self, payload: object) -> list[str]:
        if payload is None:
            return []
        loaded: object
        if isinstance(payload, str):
            try:
                loaded = _json_loads(payload)
            except orjson.JSONDecodeError:
                return []
        else:
            loaded = payload
        if not isinstance(loaded, list):
            return []
        output: list[str] = []
        for item in loaded:
            clean = normalize_text(item)
            if clean:
                output.append(clean)
        return output

    def _extract_schema_version(self, payload_json: str) -> int:
        try:
            payload = _json_loads(payload_json)
        except orjson.JSONDecodeError:
            return int(settings.MESSAGE_SCHEMA_VERSION)
        if isinstance(payload, dict):
            schema_version = payload.get("schema_version")
            if isinstance(schema_version, int):
                return schema_version
            publication = payload.get("publication")
            if isinstance(publication, dict):
                publication_version = publication.get("publication_version")
                if isinstance(publication_version, int):
                    return publication_version
                contract_version = publication.get("contract_version")
                if isinstance(contract_version, int):
                    return contract_version
        return int(settings.MESSAGE_SCHEMA_VERSION)

    def _flatten_specs(self, raw_specs: dict[str, Any]) -> list[_FlattenedSpec]:
        flattened: list[_FlattenedSpec] = []
        for key, value in raw_specs.items():
            clean_key = normalize_text(key)
            if not clean_key:
                continue
            if isinstance(value, dict) and value:
                self._flatten_spec_section(flattened, section=clean_key, payload=value, prefix=None)
                continue
            clean_value = self._coerce_spec_value(value)
            if clean_value is None:
                continue
            flattened.append(_FlattenedSpec(spec_name=clean_key, spec_value=clean_value, source_section=None))
        return flattened

    def _flatten_spec_section(
        self,
        flattened: list[_FlattenedSpec],
        *,
        section: str,
        payload: dict[str, Any],
        prefix: str | None,
    ) -> None:
        for key, value in payload.items():
            clean_key = normalize_text(key)
            if not clean_key:
                continue
            next_prefix = clean_key if prefix is None else f"{prefix} / {clean_key}"
            if isinstance(value, dict) and value:
                self._flatten_spec_section(flattened, section=section, payload=value, prefix=next_prefix)
                continue
            clean_value = self._coerce_spec_value(value)
            if clean_value is None:
                continue
            flattened.append(_FlattenedSpec(spec_name=next_prefix, spec_value=clean_value, source_section=section))

    def _coerce_spec_value(self, value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, dict):
            return _json_dumps(value)
        if isinstance(value, list):
            normalized_items: list[object] = []
            for item in value:
                if isinstance(item, dict):
                    normalized_items.append(item)
                    continue
                clean_item = normalize_text(item)
                if clean_item:
                    normalized_items.append(clean_item)
            if not normalized_items:
                return None
            return _json_dumps(normalized_items)
        return normalize_text(value)
