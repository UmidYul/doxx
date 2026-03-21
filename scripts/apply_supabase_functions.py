#!/usr/bin/env python3
"""Apply migrations/versions/002_supabase_functions.sql via psycopg2.

Run from repo root after `alembic upgrade head`.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psycopg2  # noqa: E402

from config.settings import settings  # noqa: E402

SQL = """
create or replace function increment_retry(event_id int, err text)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  update pending_events
  set retry_count = retry_count + 1,
      last_error = err,
      status = case
        when retry_count + 1 >= 10 then 'failed'
        else 'pending'
      end
  where id = event_id;
end;
$$;
"""


def main() -> int:
    dsn = (settings.DATABASE_URL_SYNC or settings.SUPABASE_DB_URL or "").strip()
    if not dsn:
        print("SUPABASE_DB_URL / DATABASE_URL_SYNC is empty — set in .env", file=sys.stderr)
        return 1
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(SQL)
        print("OK: increment_retry function applied (002_supabase_functions.sql)")
    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
