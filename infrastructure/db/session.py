from __future__ import annotations

import psycopg2
from psycopg2.extensions import connection as PGConnection

from config.settings import settings


def get_psycopg_connection() -> PGConnection:
    """Direct sync PostgreSQL connection (Scrapy pipelines, scripts, tooling)."""
    return psycopg2.connect(settings.SUPABASE_DB_URL)
