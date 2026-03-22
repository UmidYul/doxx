# Production readiness (10A)

Formal **parser → CRM** readiness for Moscraper: domains, checklist, evidence, gaps, and blockers — not a subjective “we feel done”.

## What “production-ready” means here

- **Stateless parser** delivers normalized + lifecycle-shaped events to CRM over the configured transport with **observable**, **secure**, and **governed** behavior.
- **CRM** remains system of record for dedup, persistence, and consumer-side retries.
- Readiness is **evidence-backed**: tests, docs, config, and key modules exist and checklist items reach `ready`.

## Required readiness domains

All domains in the default checklist matter; **required** items must be `ready` for a green overall assessment. Domains:

`crawl`, `normalization`, `crm_integration`, `lifecycle`, `batch_apply`, `replay_reconciliation`, `observability`, `supportability`, `security`, `performance`, `release_governance`, `documentation`.

## Accepted evidence types

| Type | Meaning |
|------|--------|
| `unit_tests` | `tests/unit` coverage for the surface |
| `contract_tests` | `tests/contracts` shape/contract tests |
| `acceptance_tests` | Regression / acceptance-style tests |
| `fixtures` | `tests/fixtures` baselines |
| `docs` | Runbooks, ADRs, integration/support docs |
| `runbook` | Operator/runbook-oriented artifacts |
| `metrics` | Profiling, cost, observability signals in code |
| `config` | Settings / Scrapy config present |
| `manual_review` | Reserved for human sign-off (optional) |

The tooling uses **pragmatic file presence** plus path rules — not a full formal methods proof.

## Blockers

A **blocking gap** typically means:

- **Security** or **CRM integration** item not `ready`, or `partial` in those domains.
- **Not started** items marked **critical** (idempotency, batch partial success, payload contract, release gates, etc.).
- **Missing store playbooks** for enabled `STORE_NAMES` (`docs/stores/<store>.md`).

Performance/cost gaps are usually **non-blocking** when status is `partial`, but still tracked.

## Reading the readiness report

- **Overall status:** `not_started` | `partial` | `ready` | `blocked`
- **Recommended action:** `continue_build` | `fix_blockers` | `prepare_go_live` | `not_ready`
- **Blocking gaps count** and **critical-risk gap count** summarize severity.
- **Domain rollup** shows worst status per domain.

Run locally:

```bash
python scripts/check_readiness.py
# or
python -m application.readiness.check_readiness
```

Exit code **non-zero** if there are **blocking** gaps.

## Go-live preparation

Move to **go-live preparation** when:

- Overall status is **`ready`**, blocking gaps **0**, and release gates (including readiness booleans) are **green**.
- CRM and ops have agreed on **cutover**, **rollback**, and **monitoring** for the first stores.

If status is **`partial`** but no blockers, finish partial items before calling it production-ready; use **`continue_build`**.

## Implementation

- Checklist: `application/readiness/readiness_registry.py`
- Evidence: `application/readiness/evidence_collector.py`
- Gaps / status: `application/readiness/gap_assessor.py`
- Policy / report: `application/readiness/readiness_policy.py`, `readiness_report.py`
- Release flags: `compute_readiness_gate_flags()` in `readiness_report.py` → merge into `evaluate_release_gates` inputs in CI.
