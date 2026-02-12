# A2 R26 Change Ledger

## Baseline
- Validate: PASS (`Errors=0`, `Warnings=0`)
- Strict validate: PASS (`Errors=0`, `Warnings=0`)
- Regression baseline: `94/94 PASS`

## Code Changes
- `prompt-dsl-system/tools/scan_graph.py`
  - Added `SCAN_GRAPH_SCHEMA_VERSION = "1.1"`.
  - Added additive payload metadata: `schema_version`, `producer_versions`, `roots_rel`, `graph_fingerprint`.
  - Added helpers:
    - `compute_graph_fingerprint_from_payload`
    - `analyze_scan_graph_payload`
  - Added `producer_versions` input to `build_scan_graph(...)`.

- `prompt-dsl-system/tools/hongzhi_plugin.py`
  - Added scan graph analysis import/usage and strict mismatch explainability fields.
  - Added machine-line additive JSON payload helper (`json='...'`).
  - Added opt-out env gate: `HONGZHI_MACHINE_JSON_ENABLE=0`.
  - Extended `HONGZHI_CAPS`/`HONGZHI_INDEX`/`HONGZHI_HINTS` with additive `json=...` and mismatch markers.
  - Summary additive fields: `mismatch_reason`, `mismatch_detail`.
  - Strengthened default scan graph reuse lookup for profile/diff (fallback history search by fingerprint).
  - profile/diff hot reuse counters now emit no-rescan command-local values (`bytes_read=0`, `java_files_indexed=0`) plus source stats.

- `prompt-dsl-system/tools/golden_path_regression.sh`
  - Added Phase32:
    - `scan_graph_schema_version_present`
    - `scan_graph_strict_mismatch_reason_emitted`
    - `discover_profile_diff_reuse_no_rescan`
    - `machine_line_json_payload_additive`
    - `governance_disabled_zero_write_still`
    - `read_only_guard_full_snapshot_ignores_limits`
  - Updated Phase29 explain parser to ignore machine-line `json='...'` and parse the actual JSON document robustly.

- Docs
  - `prompt-dsl-system/tools/PLUGIN_RUNNER.md`
  - `prompt-dsl-system/00_conventions/FACT_BASELINE.md`
  - `prompt-dsl-system/00_conventions/COMPLIANCE_MATRIX.md`

## Packaging
- No new external dependencies.
- `pyproject.toml` compatibility retained (scan_graph module remains packaged).

## Final Gate
- Regression after R26: `100/100 PASS`.
