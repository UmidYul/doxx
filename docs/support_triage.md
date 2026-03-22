# Support & triage

## Health / ETL status

- Use **structured parser logs** (`sync_event`, `dx_event`, `moscraper.*` loggers) with **correlation** (run, store, entity, batch).
- **Metrics** snapshots (if enabled) reflect delivery and retries — see observability modules.
- Prefer **summaries** over raw payloads in tickets (redaction already applied in many paths).

## Store degraded / failing

- **Operational policy** classifies store/run status from thresholds and alerts (see `domain/operational_policy`, operator support builders).
- **Degraded:** investigate mapping/coverage, HTTP errors, rate limits — check store playbook and recent deploys.
- **Failing:** treat as **critical**; consider disabling store rollout stage if supported by policy.

## Triage summary

- Human-readable triage lines from `build_human_triage_message` — **evidence rows** point to structured export, not raw log dumps.
- Use **recommended_action** as a first routing hint, not a substitute for code review.

## Runbook recommendations

- Runbook steps are **ordered**; follow the **final recommendation** when it matches policy.
- If runbook suggests **replay** or **catalog find**, confirm CRM-side idempotency and parser replay policy first.

## When safe replay is acceptable

- **Safe replay** is only when **replay policy** and CRM idempotency allow resend (same entity payload scope, no conflicting newer state).
- Prefer **replay** over **manual re-push** when automation paths exist.

## When to downgrade to `product_found`

- When delta events are **ambiguous** (missing IDs, ambiguous responses) and policy **downgrades** to `product_found` — this is intentional safety.
- Do not bypass downgrade logic in code without ADR and CRM sign-off.

## When to disable store / fail run

- **Disable store** (rollout): sustained failures, legal/ethical blocks, or CRM asks to stop.
- **Fail run:** security validation failure, invalid signing config, or non-recoverable transport misconfig.

## Safe diagnostics exports

- Use **minimized** / **redacted** exports (ETL export, diagnostic snapshots when enabled).
- **Never** paste raw secrets, full CRM responses with tokens, or unredacted PII into public channels.
- **URLs** may be trimmed in support mode — see data minimization settings.

## Escalation

- See [`OWNERSHIP_MAP.md`](../OWNERSHIP_MAP.md) for **ownership areas** and escalation paths.
