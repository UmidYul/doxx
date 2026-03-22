# Store playbook: mediapark

## Summary

- **Spider:** `mediapark` — `infrastructure/spiders/mediapark.py`
- **Host:** `mediapark.uz` (plain HTTP; no Playwright).
- **Access mode:** HTTP + shared middleware stack (stealth, rate limit, access-aware). Rotating proxy only if globally enabled.

## How it works

- Category/listing seeds from `start_category_urls`; listing pages feed product discovery.
- PDP uses **HTML + embedded JSON**; RU spec labels map to typed keys via `SPEC_FIELD_MAP` in the spider.
- Items flow: validate → normalize → sync (CRM HTTP or dry-run in dev).

## Edge cases

- **Spec labels:** Russian labels vary; new labels need mapping in `SPEC_FIELD_MAP` or extractor aliases.
- **Price/stock:** Parsed as strings then normalized; watch for currency and “уточняйте” style placeholders.

## Normalization

- `raw_specs` carry RU keys; typed mapping depends on category hint (phone, laptop, TV, …).
- Low mapping ratio triggers warnings; see regression fixtures under `tests/fixtures/regression/normalization/`.

## Known pitfalls

- Changing URL patterns without updating `allowed_domains` / pagination breaks discovery.
- Tightening `SPEC_FIELD_MAP` without regression tests can drop typed keys CRM relies on.

## Local debugging

- Short crawl: `python -m scrapy crawl mediapark -s CLOSESPIDER_ITEMCOUNT=5`
- Dry-run CRM: `DEV_MODE=true` + `DEV_DRY_RUN_DISABLE_CRM_SEND=true` (see [`DEV_WORKFLOW.md`](../../DEV_WORKFLOW.md)).
- Fixture replay: `replay_normalization_fixture("tests/fixtures/regression/normalization/laptop.json")` (same pipeline shape as mediapark-style data).

## Acceptance / gates

- Normalization regression: `tests/regression/test_normalization_regression.py`
- Contract tests for lifecycle/event shapes when changing sync payloads.
- Release gates: see [`docs/release_process.md`](../release_process.md); keep **docs** and **store playbook** updated when behavior changes.

## Rollout

- Default store in examples; treat as **reference** implementation for HTTP-first stores.
