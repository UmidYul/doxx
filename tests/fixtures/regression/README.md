# Regression fixtures (6A)

Golden samples for **normalization**, **lifecycle**, **batch apply**, and **observability** exports.  
They are **committed** and small — no auto-download from production sites.

| Path | Role |
|------|------|
| `normalization/*.json` | Raw spider-shaped items + expected typed keys / min mapping ratio |
| `lifecycle/decision_baseline.json` | Representative lifecycle decision fields |
| `batch/apply_result_baseline.json` | `CrmBatchApplyResult`-shaped dict for contract/regression |
| `observability/etl_export_baseline.json` | Minimal `parser_etl_status_v3` keys |
| `stores/` | Pointers to HTML under `tests/fixtures/stores/` |
