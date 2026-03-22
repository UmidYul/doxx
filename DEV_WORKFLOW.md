# Developer workflow (9B)

Concrete commands assume the **repository root** is the current working directory.

## Quick setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
# Optional: copy env template
copy .env.example .env
```

Unix:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

## Single-store / single-spider run

List spiders:

```powershell
python -m scrapy list
```

Run one spider (name usually matches store, e.g. `mediapark`) with a small item cap:

```powershell
python -m scrapy crawl mediapark -s CLOSESPIDER_ITEMCOUNT=5
```

Validate a store name against `STORE_NAMES` and print argv hints:

```powershell
python -m application.dev.dev_run resolve mediapark
```

Or:

```powershell
python scripts/dev_run.py resolve mediapark
```

## Dry-run (no real CRM HTTP)

Keep `TRANSPORT_TYPE=crm_http`. Enable dev mode and dry-run in `.env` or for one session:

```powershell
$env:DEV_MODE="true"
$env:DEV_DRY_RUN_DISABLE_CRM_SEND="true"
$env:MOSCRAPER_DISABLE_PUBLISH="false"
python -m scrapy crawl mediapark -s CLOSESPIDER_ITEMCOUNT=3
```

The sync pipeline still runs lifecycle/build/apply simulation; `DryRunTransport` logs `DEV_DRY_RUN_ACTIVE` and returns `action="dry_run"` (no outbound CRM request).

**Note:** With `DEV_MODE=false`, real CRM is used even if `DEV_DRY_RUN_DISABLE_CRM_SEND` is true (flag only applies together with `DEV_MODE`).

## Fixture replay (offline)

Normalization + lifecycle from regression JSON (no CRM):

```powershell
python -c "from application.dev.fixture_replay import replay_normalization_fixture; import json; print(json.dumps(replay_normalization_fixture('tests/fixtures/regression/normalization/laptop.json'), default=str))"
```

```powershell
python -c "from application.dev.fixture_replay import replay_lifecycle_fixture; import json; print(json.dumps(replay_lifecycle_fixture('tests/fixtures/regression/normalization/laptop.json'), default=str))"
```

## Acceptance / contract tests

Fast contract pass:

```powershell
python -m pytest tests/contracts -q --tb=no
```

## Release gates locally

Evaluate the same gate shape as release tooling (all flags passing baseline):

```powershell
python -c "from application.release.release_gate_evaluator import evaluate_release_gates; print(evaluate_release_gates({**{k: True for k in ['critical_unit_tests_passed','contract_tests_passed','store_acceptance_passed','payload_compatibility_passed','lifecycle_replay_safety_passed','malformed_response_regression_ok','mapping_coverage_regression_ok','parse_success_golden_ok','compatibility_core_surfaces_clean','compatibility_no_unplanned_breaking','migration_readiness_acceptable','deprecation_removal_safe','dual_shape_plan_when_needed','cost_perf_regression_gate_ok','store_efficiency_policy_ok','arch_dependency_gate_ok','arch_anti_pattern_gate_ok','architecture_lint_report_ok','arch_core_import_gate_ok']}}))"
```

(Prefer `evaluate_release_gates` from code with your real CI artifact dict.)

## Debug browser / proxy-heavy stores

Use the spider’s `custom_settings` (see spider module). For a short run:

```powershell
$env:SCRAPY_LOG_LEVEL="DEBUG"
python -m scrapy crawl uzum -s CLOSESPIDER_ITEMCOUNT=2
```

## ETL / debug summaries

With `DEV_MODE=true` and `DEV_ENABLE_DEBUG_SUMMARIES=true`, structured `dx_event` lines (`parser_dx_v1`) include compact previews:

- After normalize: `DEV_DEBUG_SUMMARY_BUILT` with `sections_included=["normalized"]` (capped per run unless `DEV_ENABLE_VERBOSE_STAGE_OUTPUT=true`).
- After lifecycle build: `sections_included=["lifecycle"]`.
- Dry-run sends: `DEV_DRY_RUN_ACTIVE` with redacted preview.

Search logs for `dx_event` or `moscraper.dx`.

## Local smoke runner

```powershell
python scripts/local_smoke.py
```

or:

```powershell
python -m application.dev.local_smoke
```

Returns a `{ "pass": bool, "steps": [...] }` summary (config, security stub, release gates baseline, fixture normalization + lifecycle, dry-run transport selection).

## Discover fixtures in tests

```powershell
python -c "from tests.helpers.fixture_tools import list_available_store_fixtures; print(list_available_store_fixtures('mediapark'))"
```

## Dev run modes (reference)

```powershell
python scripts/dev_run.py modes
```
