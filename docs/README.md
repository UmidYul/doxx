# Documentation index (9C)

Entry point for **Moscraper** (parser): architecture, operations, and store knowledge. Deep product context: [`PROJECT.md`](../PROJECT.md) (repo root).

## Quick start

- [`onboarding.md`](onboarding.md) — first day: setup, dry-run, one store, where logic lives.
- [`../DEV_WORKFLOW.md`](../DEV_WORKFLOW.md) — concrete commands (single-store, fixtures, smoke).

## Developer workflow

- [`../DEV_WORKFLOW.md`](../DEV_WORKFLOW.md) — local DX, dry-run, fixture replay, debug summaries.

## Architecture

- [`../PROJECT.md`](../PROJECT.md) — stateless parser, RabbitMQ/CRM boundaries.
- [`../ARCHITECTURE_MAP.md`](../ARCHITECTURE_MAP.md) — module map (if present).
- [`adr/README.md`](adr/README.md) — ADR index (why key decisions).

## Store development

- [`store_playbook_template.md`](store_playbook_template.md) — copy for new stores.
- [`stores/mediapark.md`](stores/mediapark.md), [`stores/uzum.md`](stores/uzum.md) — reference playbooks.
- Spiders: `infrastructure/spiders/`.

## CRM integration

- [`crm_integration.md`](crm_integration.md) — sync flow, defaults, deltas, batch/replay, change-sensitive surfaces.

## Lifecycle & replay

- ADRs: [`adr/0002-product-found-default-lifecycle.md`](adr/0002-product-found-default-lifecycle.md), [`adr/0005-replay-safe-fallbacks.md`](adr/0005-replay-safe-fallbacks.md).
- Code: `application/lifecycle/`.

## Observability & support

- [`support_triage.md`](support_triage.md) — health, triage, runbooks, safe replay, safe exports.
- Structured logs: `infrastructure/observability/`.

## Security

- `infrastructure/security/`, startup guard, outbound policy.
- See [`onboarding.md`](onboarding.md) for what not to change without review.

## Performance & rollout

- [`adr/0004-store-profiles-rollout-stages.md`](adr/0004-store-profiles-rollout-stages.md).
- Rollout/release code: `application/release/`.

## Release process

- [`release_process.md`](release_process.md) — gates, rollout, compatibility, when release blocks.

## ADRs

- [`adr/README.md`](adr/README.md) — list and conventions.

## Acceptance & fixtures

- [`fixtures_and_acceptance.md`](fixtures_and_acceptance.md) — regression fixtures, contracts, production readiness.

## Ownership & support

- [`../OWNERSHIP_MAP.md`](../OWNERSHIP_MAP.md) — areas, escalation, change-sensitive zones.
- Governance helpers: `application/governance/docs_governance.py`, `knowledge_continuity.py`.

## Production readiness (parser → CRM)

- [`production_readiness.md`](production_readiness.md) — domains, evidence, blockers, how to run `scripts/check_readiness.py`.
