-- Current scraper-side SQLite schema snapshot.
-- Flow: spider -> raw_products/images/specs -> publication_outbox.

create table if not exists schema_migrations (
    version text primary key,
    applied_at text not null
);

create table if not exists scrape_runs (
    id integer primary key autoincrement,
    run_id text not null unique,
    store_name text not null,
    spider_name text not null,
    started_at text not null,
    finished_at text null,
    status text not null,
    items_scraped integer not null default 0,
    items_persisted integer not null default 0,
    items_failed integer not null default 0,
    category_urls_json text not null default '[]',
    stats_json text not null default '{}',
    created_at text not null,
    updated_at text not null
);

create index if not exists ix_scrape_runs_store_started_at
    on scrape_runs (store_name, started_at desc);

create index if not exists ix_scrape_runs_status
    on scrape_runs (status, started_at desc);

create table if not exists raw_products (
    id integer primary key autoincrement,
    scrape_run_id text not null references scrape_runs(run_id) on delete cascade,
    store_name text not null,
    source_id text null,
    source_url text not null,
    identity_key text not null,
    title text not null,
    brand text null,
    price_raw text null,
    in_stock integer null,
    description text null,
    category_hint text null,
    external_ids_json text not null default '{}',
    payload_hash text not null,
    raw_payload_json text not null default '{}',
    structured_payload_json text not null default '{}',
    scraped_at text not null,
    publication_state text not null default 'pending',
    created_at text not null,
    updated_at text not null,
    constraint uq_raw_products_run_identity unique (scrape_run_id, identity_key)
);

create index if not exists ix_raw_products_store_name
    on raw_products (store_name, scraped_at desc);

create index if not exists ix_raw_products_scrape_run_id
    on raw_products (scrape_run_id, scraped_at desc);

create index if not exists ix_raw_products_store_source_id
    on raw_products (store_name, source_id);

create index if not exists ix_raw_products_store_source_url
    on raw_products (store_name, source_url);

create index if not exists ix_raw_products_publication_state
    on raw_products (publication_state, scraped_at desc);

create index if not exists ix_raw_products_payload_hash
    on raw_products (payload_hash);

create table if not exists raw_product_images (
    id integer primary key autoincrement,
    raw_product_id integer not null references raw_products(id) on delete cascade,
    image_url text not null,
    position integer not null,
    created_at text not null,
    updated_at text not null,
    constraint uq_raw_product_images_product_url unique (raw_product_id, image_url),
    constraint uq_raw_product_images_product_position unique (raw_product_id, position)
);

create index if not exists ix_raw_product_images_product_position
    on raw_product_images (raw_product_id, position asc);

create table if not exists raw_product_specs (
    id integer primary key autoincrement,
    raw_product_id integer not null references raw_products(id) on delete cascade,
    spec_name text not null,
    spec_value text not null,
    source_section text null,
    position integer not null,
    created_at text not null,
    updated_at text not null,
    constraint uq_raw_product_specs_product_position unique (raw_product_id, position)
);

create index if not exists ix_raw_product_specs_product_position
    on raw_product_specs (raw_product_id, position asc);

create index if not exists ix_raw_product_specs_name
    on raw_product_specs (spec_name);

create unique index if not exists ux_raw_product_specs_identity
    on raw_product_specs (raw_product_id, spec_name, spec_value, ifnull(source_section, ''));

create table if not exists publication_outbox (
    id integer primary key autoincrement,
    raw_product_id integer not null unique references raw_products(id) on delete cascade,
    event_id text not null unique,
    event_type text not null,
    schema_version integer not null,
    scrape_run_id text not null references scrape_runs(run_id) on delete cascade,
    store_name text not null,
    source_id text null,
    source_url text not null,
    payload_hash text not null,
    exchange_name text not null,
    routing_key text not null,
    payload_json text not null,
    status text not null,
    available_at text not null,
    published_at text null,
    retry_count integer not null default 0,
    last_error text null,
    lease_owner text null,
    lease_expires_at text null,
    created_at text not null,
    updated_at text not null
);

create index if not exists ix_publication_outbox_status_available
    on publication_outbox (status, available_at asc);

create index if not exists ix_publication_outbox_store_status
    on publication_outbox (store_name, status, created_at asc);

create index if not exists ix_publication_outbox_scrape_run
    on publication_outbox (scrape_run_id, created_at asc);

create index if not exists ix_publication_outbox_payload_hash
    on publication_outbox (payload_hash);

create table if not exists publication_attempts (
    id integer primary key autoincrement,
    outbox_id integer not null references publication_outbox(id) on delete cascade,
    attempt_number integer not null,
    attempted_at text not null,
    success integer not null,
    error_message text null,
    publisher_name text null,
    created_at text not null,
    constraint uq_publication_attempts_outbox_attempt unique (outbox_id, attempt_number)
);

create index if not exists ix_publication_attempts_outbox_attempted_at
    on publication_attempts (outbox_id, attempted_at desc);
