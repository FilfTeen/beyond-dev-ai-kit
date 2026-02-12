# A2 R27 Change Ledger

## Baseline
- validate: PASS
- strict validate: PASS
- regression baseline: 100/100 PASS

## Implemented
- `hongzhi_plugin.py`
  - Added CLI switch support: `--machine-json 0|1` (default 1).
  - Added runtime precedence: env `HONGZHI_MACHINE_JSON_ENABLE` overrides CLI.
  - Unified machine-line JSON encoding for:
    - `HONGZHI_CAPS`
    - `HONGZHI_INDEX`
    - `HONGZHI_HINTS`
    - `HONGZHI_STATUS`
    - `HONGZHI_GOV_BLOCK`
    - `HONGZHI_INDEX_BLOCK`
    - `HONGZHI_HINTS_BLOCK`
  - Added deterministic sort helpers for capabilities output arrays.
  - Added `metrics.candidates` deterministic ordering (`score desc`, tie-breakers).
  - Added mismatch enum normalization + `mismatch_suggestion` output.

- `scan_graph.py`
  - mismatch enum term aligned: `corrupted_cache`.

- `hongzhi_ai_kit/paths.py`
  - normalized read-only/writable resolver wrappers (no behavior regression).

- `golden_path_regression.sh`
  - Added Phase33 checks (6 total).

- Docs
  - `PLUGIN_RUNNER.md`
  - `FACT_BASELINE.md`
  - `COMPLIANCE_MATRIX.md`

## Final
- validate: PASS
- strict validate: PASS
- regression: 106/106 PASS
