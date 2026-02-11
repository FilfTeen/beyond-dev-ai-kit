# A2 R16 Change Ledger

## Functional Changes

1. Upgraded plugin contract to v3 (`hongzhi_plugin.py` -> `PLUGIN_VERSION=3.0.0`).
2. Added global state path resolver and workspace/global root separation.
3. Added capability persistence helpers with atomic writes.
4. Added smart incremental flags and reuse decision logic:
   - `--smart`
   - `--smart-max-age-seconds`
   - `--smart-min-cache-hit`
   - `--smart-max-fingerprint-drift`
5. Added capability registry write-back after successful runs:
   - `capability_index.json`
   - `latest.json`
   - `run_meta.json`
6. Added summary line contract:
   - `hongzhi_ai_kit_summary version=3.0 ...`

## Regression Changes

1. Added Phase20 (`capability_index_smoke`, 2 checks).
2. Added Phase21 (`smart_reuse_smoke`, 2 checks).
3. Added Phase22 (`governance_no_state_write`, 1 check).
4. Regression total expected checks: `37`.

## Baseline Fixes Included

1. Removed stale `skill_regression_test_ops` entry from active `skills.json`.
2. Added missing required schema fields (`prompt_template`, `output_contract`, `examples`) to governance skill YAML.

## Docs Updated

- `PLUGIN_RUNNER.md`
- `FACT_BASELINE.md`
- `COMPLIANCE_MATRIX.md`
- `HONGZHI_COMPANY_CONSTITUTION.md` (Rule 18)
