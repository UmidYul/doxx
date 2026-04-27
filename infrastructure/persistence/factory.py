from __future__ import annotations

from infrastructure.persistence.base import ScraperStore
from infrastructure.persistence.sqlite_store import SQLiteScraperStore


def resolve_scraper_db_backend(
    *,
    configured_backend: str | None,
    dsn: str | None,
) -> str:
    backend = (configured_backend or "").strip().lower()
    if backend:
        return backend
    if dsn:
        return "postgres"
    return "sqlite"


def build_scraper_store(
    *,
    backend: str,
    sqlite_path: str | None,
    postgres_dsn: str | None,
    auto_prepare: bool = False,
) -> ScraperStore:
    resolved = resolve_scraper_db_backend(configured_backend=backend, dsn=postgres_dsn)
    if resolved == "sqlite":
        return SQLiteScraperStore(sqlite_path)
    if resolved == "postgres":
        from infrastructure.persistence.postgres_store import PostgresScraperStore

        return PostgresScraperStore(postgres_dsn, auto_prepare=auto_prepare)
    raise ValueError(f"Unsupported SCRAPER_DB_BACKEND={backend!r}")
