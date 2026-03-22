# CRM integration (parser view)

## Parser → CRM flow

1. Spider produces raw items → validate → **normalize** (`NormalizedProduct` shape).
2. **Lifecycle** chooses event type (`product_found`, deltas, etc.) and builds **identity + payload hash**.
3. **Sync pipeline** batches and sends via **transport** (`crm_http` by default, or dry-run/disabled in dev/test).

CRM consumes **HTTP sync** responses; long-term DB, dedup, and full business rules are **CRM-side**. Parser stays stateless.

## `product_found` as safe default

- Default lifecycle intent is **`product_found`** unless flags and runtime IDs allow deltas.
- Downgrades to `product_found` are possible when replay/delta safety requires it (see ADRs).

## When delta events are possible

- Gated by **feature flags** (`PARSER_ENABLE_*_EVENT`, runtime delta flags, etc.).
- Requires consistent **runtime IDs** and policy (`lifecycle_policy`, replay policy).
- **Change-sensitive:** turning deltas on without CRM alignment can cause duplicate or conflicting writes.

## Batch / apply semantics

- Batching: `CRM_BATCH_SIZE`, partial success policy, retry/requeue flags per item.
- Apply results: success/rejected/retryable/ignored — classified for reconciliation and metrics.
- **Malformed batch responses** are treated as high-severity (regression tests cover this).

## Replay / idempotency / reconciliation

- **Idempotency keys** and **payload hash** align with CRM dedup expectations.
- `ReplayDecision` drives safe resend vs reconcile-only flows.
- **Reconciliation** may use catalog find / resend `product_found` per policy — see `application/lifecycle/reconciliation.py`.

## Why parser is stateless

- No durable scrape backlog or listing DB in-parser.
- “At least once” delivery and DLQ are **broker/CRM** concerns; parser fails fast on transport failure (except test `MOSCRAPER_DISABLE_PUBLISH` / dry-run).

## Change-sensitive payload surfaces

- `entity_key`, `source_id`, URLs used in hashing.
- **Typed specs** and **spec coverage** metadata if CRM matching uses them.
- **Lifecycle event type** and any field included in **payload hash** or **idempotency key**.
- **Headers / signing** for CRM HTTP (secrets, timestamps).

## Further reading

- [`adr/0002-product-found-default-lifecycle.md`](adr/0002-product-found-default-lifecycle.md)
- [`adr/0005-replay-safe-fallbacks.md`](adr/0005-replay-safe-fallbacks.md)
- [`docs/release_process.md`](release_process.md)
