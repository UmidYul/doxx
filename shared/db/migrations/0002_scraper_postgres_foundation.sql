create schema if not exists scraper;

create table if not exists scraper.schema_migrations (
    version text primary key,
    applied_at timestamptz not null
);

create table if not exists scraper.scrape_runs (
    id bigserial primary key,
    run_id text not null unique,
    store_name text not null,
    spider_name text not null,
    started_at timestamptz not null,
    finished_at timestamptz,
    status text not null,
    items_scraped integer not null default 0,
    items_persisted integer not null default 0,
    items_failed integer not null default 0,
    category_urls_json jsonb not null default '[]'::jsonb,
    stats_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null,
    updated_at timestamptz not null
);

create index if not exists ix_scraper_scrape_runs_store_started_at
    on scraper.scrape_runs (store_name, started_at desc);

create index if not exists ix_scraper_scrape_runs_status
    on scraper.scrape_runs (status, started_at desc);

create table if not exists scraper.raw_products (
    id bigserial primary key,
    scrape_run_id text not null references scraper.scrape_runs(run_id) on delete cascade,
    store_name text not null,
    source_id text,
    source_url text not null,
    identity_key text not null,
    title text not null,
    brand text,
    price_raw text,
    in_stock boolean,
    description text,
    category_hint text,
    external_ids_json jsonb not null default '{}'::jsonb,
    payload_hash text not null,
    raw_payload_json jsonb not null default '{}'::jsonb,
    structured_payload_json jsonb not null default '{}'::jsonb,
    scraped_at timestamptz not null,
    publication_state text not null default 'pending',
    created_at timestamptz not null,
    updated_at timestamptz not null,
    constraint uq_scraper_raw_products_run_identity unique (scrape_run_id, identity_key)
);

create index if not exists ix_scraper_raw_products_store_name
    on scraper.raw_products (store_name, scraped_at desc);

create index if not exists ix_scraper_raw_products_scrape_run_id
    on scraper.raw_products (scrape_run_id, scraped_at desc);

create index if not exists ix_scraper_raw_products_store_source_id
    on scraper.raw_products (store_name, source_id);

create index if not exists ix_scraper_raw_products_store_source_url
    on scraper.raw_products (store_name, source_url);

create index if not exists ix_scraper_raw_products_publication_state
    on scraper.raw_products (publication_state, scraped_at desc);

create index if not exists ix_scraper_raw_products_payload_hash
    on scraper.raw_products (payload_hash);

create table if not exists scraper.raw_product_images (
    id bigserial primary key,
    raw_product_id bigint not null references scraper.raw_products(id) on delete cascade,
    image_url text not null,
    position integer not null,
    created_at timestamptz not null,
    updated_at timestamptz not null,
    constraint uq_scraper_raw_product_images_url unique (raw_product_id, image_url),
    constraint uq_scraper_raw_product_images_position unique (raw_product_id, position)
);

create index if not exists ix_scraper_raw_product_images_product_position
    on scraper.raw_product_images (raw_product_id, position asc);

create table if not exists scraper.raw_product_specs (
    id bigserial primary key,
    raw_product_id bigint not null references scraper.raw_products(id) on delete cascade,
    spec_name text not null,
    spec_value text not null,
    source_section text,
    position integer not null,
    created_at timestamptz not null,
    updated_at timestamptz not null,
    constraint uq_scraper_raw_product_specs_position unique (raw_product_id, position)
);

create index if not exists ix_scraper_raw_product_specs_product_position
    on scraper.raw_product_specs (raw_product_id, position asc);

create index if not exists ix_scraper_raw_product_specs_name
    on scraper.raw_product_specs (spec_name);

create unique index if not exists ux_scraper_raw_product_specs_identity
    on scraper.raw_product_specs (raw_product_id, spec_name, spec_value, coalesce(source_section, ''));

create table if not exists scraper.publication_outbox (
    id bigserial primary key,
    raw_product_id bigint not null unique references scraper.raw_products(id) on delete cascade,
    event_id text not null unique,
    event_type text not null,
    schema_version integer not null,
    scrape_run_id text not null references scraper.scrape_runs(run_id) on delete cascade,
    store_name text not null,
    source_id text,
    source_url text not null,
    payload_hash text not null,
    exchange_name text not null,
    routing_key text not null,
    payload_json jsonb not null,
    status text not null,
    available_at timestamptz not null,
    published_at timestamptz,
    retry_count integer not null default 0,
    last_error text,
    lease_owner text,
    lease_expires_at timestamptz,
    created_at timestamptz not null,
    updated_at timestamptz not null,
    constraint ck_scraper_publication_outbox_status
        check (status in ('pending', 'leased', 'retryable', 'failed', 'published'))
);

create index if not exists ix_scraper_publication_outbox_status_available
    on scraper.publication_outbox (status, available_at asc);

create index if not exists ix_scraper_publication_outbox_store_status
    on scraper.publication_outbox (store_name, status, created_at asc);

create index if not exists ix_scraper_publication_outbox_scrape_run
    on scraper.publication_outbox (scrape_run_id, created_at asc);

create index if not exists ix_scraper_publication_outbox_payload_hash
    on scraper.publication_outbox (payload_hash);

create index if not exists ix_scraper_publication_outbox_lease_expires
    on scraper.publication_outbox (lease_expires_at asc)
    where status = 'leased';

create table if not exists scraper.publication_attempts (
    id bigserial primary key,
    outbox_id bigint not null references scraper.publication_outbox(id) on delete cascade,
    attempt_number integer not null,
    attempted_at timestamptz not null,
    success boolean not null,
    error_message text,
    publisher_name text,
    created_at timestamptz not null,
    constraint uq_scraper_publication_attempts_outbox_attempt unique (outbox_id, attempt_number)
);

create index if not exists ix_scraper_publication_attempts_outbox_attempted_at
    on scraper.publication_attempts (outbox_id, attempted_at desc);

create or replace function scraper.requeue_outbox(
    p_event_id text default null,
    p_scrape_run_id text default null,
    p_store_name text default null,
    p_statuses text[] default null,
    p_limit integer default null
)
returns integer
language plpgsql
as $$
declare
    v_count integer := 0;
    v_raw_product_ids bigint[] := '{}'::bigint[];
begin
    with updated as (
        update scraper.publication_outbox po
           set status = 'pending',
               available_at = now(),
               published_at = null,
               last_error = null,
               lease_owner = null,
               lease_expires_at = null,
               updated_at = now()
         where po.id in (
                select inner_po.id
                  from scraper.publication_outbox inner_po
                 where (p_event_id is null or inner_po.event_id = p_event_id)
                   and (p_scrape_run_id is null or inner_po.scrape_run_id = p_scrape_run_id)
                   and (p_store_name is null or inner_po.store_name = p_store_name)
                   and (coalesce(cardinality(p_statuses), 0) = 0 or inner_po.status = any(p_statuses))
                 order by inner_po.created_at asc
                 limit coalesce(nullif(p_limit, 0), 2147483647)
                 for update
           )
        returning po.raw_product_id
    )
    select count(*), coalesce(array_agg(raw_product_id), '{}'::bigint[])
      into v_count, v_raw_product_ids
      from updated;

    if v_count > 0 then
        update scraper.raw_products
           set publication_state = 'pending',
               updated_at = now()
         where id = any(v_raw_product_ids);
    end if;

    return v_count;
end;
$$;

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'scraper_runtime') then
        grant usage on schema scraper to scraper_runtime;
        grant select, insert, update on scraper.scrape_runs to scraper_runtime;
        grant select, insert, update on scraper.raw_products to scraper_runtime;
        grant select, insert, update, delete on scraper.raw_product_images to scraper_runtime;
        grant select, insert, update, delete on scraper.raw_product_specs to scraper_runtime;
        grant select, insert, update on scraper.publication_outbox to scraper_runtime;
        grant usage, select on all sequences in schema scraper to scraper_runtime;
    end if;

    if exists (select 1 from pg_roles where rolname = 'publisher_runtime') then
        grant usage on schema scraper to publisher_runtime;
        grant select, update on scraper.publication_outbox to publisher_runtime;
        grant select, update on scraper.raw_products to publisher_runtime;
        grant select, insert, update on scraper.publication_attempts to publisher_runtime;
        grant execute on function scraper.requeue_outbox(text, text, text, text[], integer) to publisher_runtime;
        grant usage, select on all sequences in schema scraper to publisher_runtime;
    end if;
end;
$$;

insert into scraper.schema_migrations (version, applied_at)
values ('0002_scraper_postgres_foundation', now())
on conflict (version) do nothing;
