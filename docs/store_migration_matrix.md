# Store Migration Matrix

This document is the stage-6 migration view for all real stores found in the old and new repos.

## Store inventory

Old `E-katalog` reference stores:

- `mediapark`
- `texnomart`
- `alifshop`

Current `doxx` stores:

- `mediapark`
- `texnomart`
- `uzum`
- `alifshop`

`uzum` has no old `E-katalog` counterpart, so it was migrated to the same ingestion contract without pretending that an old parser existed for it.

## Migration plan by store

| Store | Reference basis | Source discovery strategy | Listing flow | PDP flow | `source_id` strategy | `raw_specs` strategy | Image strategy | Brittle points | Current stage |
|---|---|---|---|---|---|---|---|---|---|
| `mediapark` | direct old MediaPark parser | HTML anchors plus escaped Next.js payloads | category seeds -> nested category hubs -> synthetic pagination | JSON-LD-first PDP with HTML/script fallbacks | numeric slug tail from `/products/view/...` | `__next_f`, `__NEXT_DATA__`, JSON-LD, tables, body text | JSON-LD, Next.js payloads, `og:image`, `img` tags | Next.js payload drift, partial PDP renders | migrated reference implementation |
| `texnomart` | partial old family reference plus current resilient selectors | anchors and serialized product hrefs | phone category seed -> filtered subcategories -> explicit or synthetic pagination | JSON-LD-first PDP with price/spec HTML fallback | query identifiers, numeric path tail, slug fallback | JSON-LD `additionalProperty`, tables, `dl`, characteristic rows | JSON-LD images and `img` attrs | markup drift, installment-price confusion, browser need on live pages | migrated, needs live tuning |
| `uzum` | no old counterpart | browser-rendered anchors and serialized hrefs | Playwright category load -> controlled scroll -> synthetic pagination | hydrated PDP with JSON-LD and HTML fallback | `skuId` first, then numeric path id | JSON-LD `additionalProperty`, HTML `itemprop`, tables | JSON-LD, meta images, `img` attrs | heavy JS, timing sensitivity, browser budgets | migrated, browser-specific tuning required |
| `alifshop` | direct old Alifshop parser | moderated-offer links in anchors and raw HTML | phone category seeds -> nested phone categories -> explicit or synthetic pagination | meta-tag-first PDP with HTML fallback | numeric tail in moderated-offer slug, then query fallback | bordered characteristics rows and body-text fallback | `og:image`, `twitter:image`, Fortifai CDN links, `img` attrs | utility-class drift, title boilerplate, moderated slug format changes | migrated, minor selector tuning expected |

## Acceptance matrix

Coverage is enforced in `tests/acceptance/test_store_ingestion_matrix.py` and `tests/acceptance/test_store_acceptance.py`.

| Store | Listing coverage | PDP coverage | `source_id` coverage | `raw_specs` coverage | Image coverage | Outbox creation | Publication path |
|---|---|---|---|---|---|---|---|
| `mediapark` | yes | yes | yes | yes | yes | yes | yes, via publisher worker contract |
| `texnomart` | yes | yes | yes | yes | yes | yes | yes, via publisher worker contract |
| `uzum` | yes | yes | yes | yes | yes | yes | yes, via publisher worker contract |
| `alifshop` | yes | yes | yes | yes | yes | yes | yes, via publisher worker contract |

Notes:

- The acceptance matrix verifies `store spider -> scraper DB -> outbox -> publisher worker` with a stub broker.
- Live RabbitMQ publication remains covered separately by `tests/integration/test_rabbit_publish.py`.

## Standard now enforced across stores

- all spiders emit the same minimal raw item contract
- all items are persisted into scraper DB before any publication step
- all stores create outbox rows
- all Rabbit publication goes through the standalone publisher service
- scraper responsibility ends at RabbitMQ

## Stores that still need store-specific tuning

- `texnomart`: live markup and price-block drift
- `uzum`: browser timing, scroll depth, resource budgets
- `alifshop`: characteristics block CSS drift
- `mediapark`: Next.js payload shape changes, but the architectural pattern is already the baseline
