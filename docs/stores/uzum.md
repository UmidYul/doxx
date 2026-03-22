# Store playbook: uzum

## Summary

- **Spider:** `uzum` — `infrastructure/spiders/uzum.py`
- **Host:** `uzum.uz`
- **Access mode:** **Playwright required** — `scrapy-playwright` download handlers in `custom_settings`. Install: `pip install '.[playwright]'` and `playwright install`.

## How it works

- Heavy JS storefront; browser renders listing/PDP (not plain static HTML).
- `start_category_urls` seeds the homepage; **listing → PDP extraction is still evolving** — keep spider contract aligned with `BaseProductSpider` and validation.

## Edge cases

- **Concurrency:** Lower `CONCURRENT_REQUESTS` in spider custom settings than HTTP stores; browser is heavier.
- **Timeouts / flaky loads:** May need Playwright options or retry policy tuned per environment.

## Anti-bot / ops

- Expect browser budget and resource metrics to matter (performance governance). See `OWNERSHIP_MAP.md` performance/rollout area.
- If rotating proxy is enabled globally, validate behavior with Playwright (not all stacks are equal).

## Normalization

- Same normalize pipeline as other stores once items are shaped; **field coverage depends on** what extraction yields.
- Add or extend fixtures when PDP extraction stabilizes.

## Known pitfalls

- Running `uzum` without Playwright installed fails at handler level — document in onboarding.
- Treating `is_product_page` / PDP logic as stable before listing extraction is complete can cause empty runs.

## Local debugging

- `python -m scrapy crawl uzum -s CLOSESPIDER_ITEMCOUNT=2`
- `SCRAPY_LOG_LEVEL=DEBUG` for browser/network issues.
- Prefer dry-run CRM when testing delivery: [`DEV_WORKFLOW.md`](../../DEV_WORKFLOW.md).

## Acceptance / gates

- Contract tests for parser events and lifecycle when payloads change.
- Performance/cost gates: browser stores are **sensitive** to resource regressions.

## Rollout

- Prefer **canary** or **disabled** until listing/PDP coverage is production-ready; update this playbook when milestones change.
