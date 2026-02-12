# A2_R25 Change Ledger

## Functional Changes
1. Added `scan_graph.py`:
- Single-pass indexing (`file_index`, `java_hints`, `template_hints`, `io_stats`, `cache_key`).
- Workspace cache support (`scan_cache/<cache_key>.json`).
- CLI support for standalone smoke/regression.

2. Updated `hongzhi_plugin.py`:
- Discover now builds and consumes scan graph.
- Added scan graph spot-check mismatch detection.
- Added strict mismatch exit code `25` (`exit_hint=scan_graph_mismatch`).
- Added `scan-graph` subcommand (governance-gated, workspace-only writes).
- Added profile/diff scan graph reuse flags:
  - `profile --scan-graph`
  - `diff --old-scan-graph --new-scan-graph`
- Added `scan_graph` payload to capabilities outputs.
- Extended summary line with scan graph telemetry fields.

3. Updated scanners/tools:
- `module_profile_scanner.py` supports `--scan-graph` reuse.
- `cross_project_structure_diff.py` supports graph-based class/template input.

4. Regression updates:
- Added Phase31 (8 checks) in `golden_path_regression.sh`.
- Added fixture `case7_scan_graph_weird_annotations`.

5. Documentation/baselines:
- `PLUGIN_RUNNER.md`
- `FACT_BASELINE.md`
- `COMPLIANCE_MATRIX.md`

## Compatibility Notes
- Existing machine lines are preserved; new fields are additive.
- Existing Phase1~30 checks preserved and kept runnable.
