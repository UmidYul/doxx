# Parser → CRM go-live policy (10C)

Formal **go / no-go**, **cutover checklist**, **rollback triggers**, and **stabilization windows** live in code under `application/go_live/` and `domain/go_live.py`. This doc is the operator-facing summary; thresholds come from `config/settings.py` (go-live + stabilization blocks).

## What must be true before go-live

All **required exit criteria** from `get_default_exit_criteria()` / `evaluate_exit_criteria()` must pass when settings demand it, including typically:

- Readiness not blocked (and `GO_LIVE_REQUIRE_READINESS_READY` requires overall **ready**).
- Release gates clean (`ReleaseReadinessSummary` when `GO_LIVE_REQUIRE_RELEASE_GATES_PASS`).
- CRM payload + lifecycle checklist items (or explicit status flags in `status_summary`).
- Security and observability baselines, rollout policy present, store acceptance and playbooks for enabled stores.
- Dry-run, smoke, and contract checks true in `status_summary`.
- First launch on **canary** for enabled stores when `GO_LIVE_CANARY_ONLY_FIRST`.

Plus **blocking cutover checklist** rows from `build_cutover_checklist()` must be completed (production config, keys, observability export, dry-run/smoke, release review, etc.).

## Go / no-go model

`assess_go_live()` returns a `GoLiveAssessment`:

| Decision | Meaning |
| --- | --- |
| `go` | Required exit criteria pass, cutover checklist blocking rows complete, overall readiness **ready**. |
| `no_go` | Any required exit criterion failed and/or blocking cutover item open. |
| `go_with_constraints` | No hard blockers, but overall readiness **partial** (with `GO_LIVE_REQUIRE_READINESS_READY` off for “partial” path) and/or documented rollout caveats in constraints. |

`decide_go_live()` encodes this; `explain_no_go_reasons()` lists failed criterion codes and cutover blockers.

## First launch must be canary

With `GO_LIVE_CANARY_ONLY_FIRST`, enabled stores (from `STORE_NAMES`) must appear under **canary** in the rollout snapshot (`stores_by_stage`), not **partial** or **full**, unless `canary_exception_approved` is set in `status_summary`. Violations fail `exit.canary_scope_first_launch` and `cutover.canary_stage`.

## Stabilization windows

`build_stabilization_checkpoints()` defines three checkpoints:

| Window | Focus |
| --- | --- |
| **0–4h** | Critical/high alert budgets, apply/transport sanity, scope stability (`STABILIZATION_MAX_*_ALERTS`, `STABILIZATION_BLOCK_ON_CRITICAL_ALERTS`). |
| **4–24h** | Rejected-item and reconciliation health vs `STABILIZATION_MAX_REJECTED_ITEM_RATE`, `STABILIZATION_MAX_UNRESOLVED_RECONCILIATION_RATE`. |
| **24–72h** | Malformed response persistence, suspected contract drift, perf/support load. |

`evaluate_stabilization()` updates `passed` per checkpoint from `status_summary`, `alerts`, and `metrics`. `summarize_stabilization_state()` produces a `LaunchOutcome` (`successful`, `stabilizing`, `degraded`, `rolled_back`).

## Rollback / degrade triggers

`get_default_rollback_triggers()` lists advisory triggers; `evaluate_rollback_triggers()` marks which fire from `status_summary` and `recent_alerts` (no auto-execution). Actions include `rollback`, `degrade_store`, `pause_store`, `disable_feature`, `investigate`.

## Definition of successful launch

Operational success: **all stabilization checkpoints pass**, **no critical rollback triggers fired**, and business sign-off to move `launch_stage` toward `steady_state`. A **degraded** outcome means high-severity triggers or failed mid-window checks without full rollback.

## Transition to steady state

After 72h stability, promote rollout only via existing rollout policy and release gates; re-run `assess_go_live` when scope widens or contract changes.

## How this relates to readiness and release reports

- **Readiness** and **roadmap** show engineering gaps; **go-live** adds operational cutover rules. `build_production_readiness_report(...)` attaches a **go-live assessment snapshot** when `ENABLE_GO_LIVE_POLICY` is on.
- **Release summary** `overall_passed` is explicitly **not** automatic go-live approval (`go_live_note` in `build_release_report`).

Structured logs: `GO_LIVE_*`, `CUTOVER_*`, `ROLLBACK_*`, `STABILIZATION_*`, `LAUNCH_OUTCOME_*` via `log_go_live_event` (`parser_go_live_v1`).
