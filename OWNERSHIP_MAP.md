# Ownership map (9C)

Roles are **logical** (who answers first), not HR titles. Escalation = who to pull in when the primary owner is unavailable or the change is cross-cutting.

## Store spiders / crawling

| | |
|---|---|
| **Scope** | Scrapy spiders, listing/PDP extraction, pagination, store-specific selectors. |
| **Change-sensitive** | URL shapes, `allowed_domains`, rate limits, Playwright opt-in, raw item shape fed to validate/normalize. |
| **Key modules** | `infrastructure/spiders/`, `infrastructure/middlewares/` |
| **Escalation** | Access/anti-bot policy owner → normalization (if spec keys change) → release/rollout (if store enablement changes). |

## Normalization / typed specs

| | |
|---|---|
| **Scope** | Light normalization, `raw_specs` / typed mapping, spec coverage, quality metadata. |
| **Change-sensitive** | `entity_key` inputs, typed keys used by CRM matching, mapping ratios, deprecation of fields. |
| **Key modules** | `application/normalization/`, `application/extractors/`, `infrastructure/pipelines/normalize_pipeline.py` |
| **Escalation** | Lifecycle/CRM semantics if event types or payload hashes change → contract/compatibility. |

## Lifecycle / CRM semantics

| | |
|---|---|
| **Scope** | Event type selection, replay/idempotency, reconciliation, delta vs `product_found`. |
| **Change-sensitive** | Default event type, delta flags, idempotency keys, payload hash rules. |
| **Key modules** | `application/lifecycle/`, `domain/crm_lifecycle.py`, `domain/parser_event.py` |
| **Escalation** | CRM integration owner → ADR review for contract changes. |

## Transport / sync delivery

| | |
|---|---|
| **Scope** | CRM HTTP batch/apply, retries, dry-run in dev, disabled transport for tests. |
| **Change-sensitive** | Endpoints, headers, signing, batch semantics, apply result classification. |
| **Key modules** | `infrastructure/transports/`, `infrastructure/pipelines/sync_pipeline.py` |
| **Escalation** | Security (signing/secrets) → observability (delivery alerts). |

## Observability / support

| | |
|---|---|
| **Scope** | Structured logs, correlation, triage/runbook messages, metrics, ETL-friendly summaries. |
| **Change-sensitive** | Message codes, payload summaries, anything PII-adjacent in logs. |
| **Key modules** | `infrastructure/observability/`, `application/operator_support/` (if present) |
| **Escalation** | On-call / support lead; security if exports contain sensitive data. |

## Security

| | |
|---|---|
| **Scope** | Secrets, redaction, outbound URL/proxy policy, request signing, startup validation. |
| **Change-sensitive** | Parser keys, signing modes, allowlists, anything that weakens egress controls. |
| **Key modules** | `infrastructure/security/` |
| **Escalation** | Security owner mandatory for production-facing changes. |

## Performance / rollout / release

| | |
|---|---|
| **Scope** | Resource limits, backpressure, rollout stages, release gates, cost/perf regression signals. |
| **Change-sensitive** | Gate thresholds, store rollout flags, canary percentages, architecture lint rules. |
| **Key modules** | `application/release/`, `application/governance/`, perf collectors |
| **Escalation** | Release owner; docs/knowledge when playbooks or ADRs must be updated. |

## Docs / fixtures / acceptance

| | |
|---|---|
| **Scope** | `docs/`, `OWNERSHIP_MAP.md`, store playbooks, ADRs, regression fixtures, contract tests. |
| **Change-sensitive** | Anything that defines “done” for a store or a contract; missing docs block knowledge continuity gates. |
| **Key modules** | `docs/`, `tests/fixtures/`, `tests/contracts/**` |
| **Escalation** | Tech lead + whoever owns the store in the playbook. |

---

Update this file when **ownership areas** or **escalation paths** change. New stores: add `docs/stores/<store>.md` before enabling in production.
