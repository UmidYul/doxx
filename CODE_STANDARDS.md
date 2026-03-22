# Internal engineering standards (9A)

Naming and placement conventions for long-term maintainability. **Not** a style guide for every line of code.

## Domain models (`domain/`)

- **Types:** `PascalCase` for models (`RawProduct`, `ParserSyncEvent`).
- **Files:** one primary concept per file or small cohesive group (`crm_apply_result.py`, `parser_event.py`).
- **Versioning:** explicit `schema_version` fields where messages are versioned.

## Application modules (`application/`)

- **Policies / rules:** `*_policy.py`, `*_engine.py` (e.g. `rollout_policy_engine.py`).
- **Builders:** `*_builder.py` when constructing complex DTOs (`lifecycle_builder.py`).
- **Registries:** `*_registry.py` for lookup tables (`spec_registry.py`, `deprecation_registry.py`).
- **Guards / gates:** `*_guard.py`, `*_gate_runner.py` for allow/deny decisions.
- **Advisors / summaries:** `*_advisor.py`, `*_summary.py` for human-oriented output.
- **Avoid:** spider-specific HTML selectors here.

## Infrastructure (`infrastructure/`)

- **Transports:** `infrastructure/transports/*_transport.py`.
- **Pipelines:** `*pipeline*.py` under `infrastructure/pipelines/`.
- **Spiders:** `infrastructure/spiders/<store>.py` or descriptive name; **store-specific** file names match store slug (`mediapark.py`, `uzum.py`).
- **Exporters / snapshots:** `*_exporter.py`, `*_snapshot.py` under `performance/` or `observability/`.

## Config & settings (`config/`)

- **Settings class:** `Settings` in `config/settings.py`; fields `UPPER_SNAKE_CASE`.
- **Feature flags:** `ENABLE_*`, `DISABLE_*`, or grouped under rollout settings—document in `.env.example` when user-visible.

## Message codes (`infrastructure/observability/message_codes.py`)

- **Format:** `SCREAMING_SNAKE_CASE`, stable string constants.
- **Prefix by area:** e.g. `PERF_*`, `RESOURCE_*`, `COST_*`, `ARCH_*` (9A)—avoid reusing the same string for different meanings.

## Tests (`tests/`)

- **Files:** `test_<module>.py` under `tests/unit/`, `tests/contracts/`, etc.
- **Names:** `test_<behavior>_<condition>()`; keep golden data in `tests/fixtures/` or adjacent dirs.

## Governance & lint (9A)

- **Architecture helpers:** `application/governance/` — `dependency_policy`, `architecture_lint`, `code_placement`, `anti_patterns`.

When in doubt, run `decide_code_placement()` heuristics or open `ARCHITECTURE_MAP.md`.
