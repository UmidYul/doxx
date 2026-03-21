-- Run in Supabase SQL Editor once after: alembic upgrade head
-- File: migrations/versions/002_supabase_functions.sql

-- increment_retry: atomic counter update (supabase-py RPC; client cannot increment atomically)
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
