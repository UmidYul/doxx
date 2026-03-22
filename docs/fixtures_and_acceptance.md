# Fixtures & acceptance

## What fixtures exist

- **Regression normalization:** `tests/fixtures/regression/normalization/*.json` — `raw_item`, thresholds, expected typed keys.
- **Lifecycle / batch / observability baselines:** `tests/fixtures/regression/**` — keep stable for contract/regression tests.
- **Dev replay:** use `application.dev.fixture_replay` (see [`DEV_WORKFLOW.md`](../DEV_WORKFLOW.md)).

## Adding a new fixture

1. Prefer **minimal** JSON that reproduces the bug or edge case.
2. Put under `tests/fixtures/regression/...` with a clear name.
3. Reference it from a test or regression test module.
4. For store-specific behavior, note the path in the **store playbook** (`docs/stores/<store>.md`).

## Acceptance for a store

- **Normalization:** mapping ratio ≥ store baseline where applicable; required typed keys present.
- **Lifecycle/sync:** contract tests pass for event shapes you emit.
- **Operational:** spider runs without systematic 4xx/5xx; access policy not in constant escalation.
- **Docs:** `docs/stores/<store>.md` filled and linked from [`docs/README.md`](README.md).

## Running locally

```bash
pytest tests/regression -q
pytest tests/contracts -q
pytest tests/unit -q
```

Use targeted paths while iterating. Full suite before merge per team policy.

## Contract tests

- `tests/contracts/**` — schema/shape contracts.
- Failures often indicate **CRM/parser contract drift** — fix code or coordinate a versioned migration.

## Production-ready checklist

- [ ] Store playbook complete and reviewed.
- [ ] Enabled in `STORE_NAMES` only after rollout policy allows.
- [ ] Regression fixtures for representative SKUs/categories.
- [ ] Release gates green including **documentation** (9C) when enforced.
