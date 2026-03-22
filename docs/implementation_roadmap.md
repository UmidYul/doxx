# Parser implementation roadmap (10B)

This document describes how Moscraper turns **readiness gaps** into a **phased implementation plan** without big-bang refactors. Executable logic lives in `application/readiness/` (`roadmap_planner`, `roadmap_dependencies`, `phase_policy`, `prioritization`, `roadmap_report`) and domain types in `domain/implementation_roadmap.py`.

## Phase overview

| Phase | Intent |
| --- | --- |
| **foundation** | Baseline crawl, CRM HTTP transport, security minimum, smoke-level tests. |
| **go_live_baseline** | Observability and support minimum, lifecycle/batch safety, release gates, contract stability for canary / first prod. |
| **post_launch_hardening** | Replay/reconciliation depth, cost/perf signals, operator tooling, docs/runbooks from real traffic. |
| **scale_maturity** | Multi-store patterns, resource budgets, advanced governance and deprecation handling. |

Entry and exit criteria strings are returned by `get_phase_entry_criteria` / `get_phase_exit_criteria` in `application/readiness/phase_policy.py`. Whether the **current** `ProductionReadinessReport` satisfies those gates is evaluated by `can_enter_phase` / `can_exit_phase` (pragmatic rollup over checklist domains + blockers).

## What is required before go-live

Treat as **must-close before cutover** (also flagged `blocking_for_go_live` on derived `RoadmapItem`s when the source gap is blocking):

- Security baseline and outbound/redaction guardrails.
- CRM integration: transport, auth, payload contract alignment with CRM consumers.
- Crawl correctness for in-scope stores (pagination, dedup guards as applicable).
- Lifecycle / batch delivery semantics safe for CRM (no silent data loss).
- Minimum observability: structured logs, failure classification, operator-facing signals.
- Release governance: CI/release gates aligned with rollout policy.
- Documentation/support minimum: store playbooks and handoff path for on-call.

Items in **foundation** and **go_live_baseline** phases, or any item with `blocking_for_go_live=True`, belong in the **go-live critical path** until closed.

## What can wait until post-launch

Typical **deferrable** work (mapped to **post_launch_hardening** or **scale_maturity** when non-blocking):

- Advanced performance tuning and cost governance after first real traffic.
- Extended replay matrices and reconciliation drill-down beyond baseline.
- Deep operator UX and secondary runbooks.
- Maturity-only documentation and non-blocking supportability polish.

The roadmap report lists **post-launch item codes** explicitly; `split_go_live_vs_post_launch` separates scopes for planning.

## Critical path

The **critical path** is the longest prerequisite chain inferred from `RoadmapDependency` edges (`infer_critical_path` in `roadmap_dependencies.py`). It is an **ordering aid**, not a duration estimate. Dependencies encode policy such as:

- Security baseline before CRM integration hardening.
- Crawl framework before CRM delivery integration.
- Foundation work before observability for canary.
- Observability before widening rollout via release gates.
- CRM transport before lifecycle delivery semantics.
- Store playbooks/docs before support handoff.

## Ownership / workstream view

Each `RoadmapItem` has `workstream` (`crawl`, `crm_integration`, `observability`, …) and `recommended_owner_area`. Parallel work is approximated by **dependency layers** from `detect_parallelizable_items` (items in the same layer have no directed edge between them in the inferred graph).

## How to use this with the readiness report

1. Build `ProductionReadinessReport` via `build_production_readiness_report` (checklist + gaps + evidence).
2. The report is **automatically enriched** with:
   - `roadmap_summary` — counts, critical path, parallel layers, top ranked codes.
   - `roadmap_critical_path` — ordered item codes.
   - `roadmap_phase_hints_by_domain` — for **blocked** domains, `phase/workstream` from the worst gap in that domain.
   - `roadmap_top_blocker_item_codes` — prioritized blocking roadmap items.
3. Use `build_human_roadmap_report` on the full `ImplementationRoadmap` from `build_default_roadmap_from_gaps` when you need a standalone narrative.
4. Optional structured logs: `build_default_roadmap_from_gaps(..., emit_structured_logs=True)` and `can_enter_phase` / `can_exit_phase` with `emit_structured_logs=True` emit `ROADMAP_*` and `PHASE_*` codes (see `infrastructure/observability/message_codes.py`).

This sequencing helps the team **pick one phase and a small set of streams** instead of executing every gap at once.
