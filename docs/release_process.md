# Release process

## Release gates

- **Quality gates** map CI/tooling booleans into pass/fail (`application/release/release_gate_evaluator.py`).
- **Critical** gates block release; **high** severity failures count as critical failures in summary.
- **Docs / knowledge (9C):** required documentation, store playbooks for enabled stores, coverage, and knowledge continuity flags must be green when CI passes them.

## Canary / partial / full rollout

- **Store rollout** stages and feature flags are described in ADR `0004-store-profiles-rollout-stages.md` and rollout policy code.
- **Canary:** small slice of traffic or stores; watch observability and cost signals.
- **Partial / full:** promote when gates and health checks pass.

## Rollback advisory

- **Auto-rollback advice** may emit when rollout guards detect failing status — treat as advisory; confirm with CRM and ops.
- **Rollback** = revert deploy + possibly **disable store** in rollout config.

## Compatibility checks

- **Contract evolution** gates: core surfaces, breaking changes, migration readiness, deprecation policy.
- **Payload compatibility** and **lifecycle replay safety** must pass before widening rollout.

## Deprecation / shadow / dual-shape

- **Shadow fields** and **dual-shape** outputs follow compatibility modules — do not remove deprecated paths without a migration plan and gate.

## Performance / cost regression gates

- **Cost/perf** and **store efficiency** gates catch regressions in resource use and overhead.
- Failing these blocks release when configured as critical.

## When release is blocked

- Any **critical** gate failure → `block_release` recommendation.
- **Warnings** → `release_with_caution` (document in changelog).
- **Documentation gaps** (9C): missing required docs, missing store playbooks for enabled stores, or critical knowledge continuity risk — fix or waive with explicit approval and ticket.

## Practical checklist

1. Unit + contract + acceptance + regression tests green.
2. Architecture lint / dependency gates as required.
3. **Docs** present (index, onboarding, ownership, CRM, support, release, fixtures, ADR index).
4. **Store playbooks** for each `STORE_NAMES` entry.
5. Changelog / release notes updated for operator-facing changes.
