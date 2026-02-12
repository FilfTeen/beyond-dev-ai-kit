# A1 R26 Impact Tree

## Scope
- Target: `prompt-dsl-system/**`
- No writes to analyzed target repos (`repo_root`) introduced.

## Primary Changes
1. Scan Graph contract additive metadata
- Files: `prompt-dsl-system/tools/scan_graph.py`, `prompt-dsl-system/tools/hongzhi_plugin.py`
- Impact:
  - Adds `schema_version`, `producer_versions`, `graph_fingerprint` to scan graph payload.
  - Enables strict mismatch explainability (`mismatch_reason`, `mismatch_detail`).

2. Machine-line additive JSON payload
- Files: `prompt-dsl-system/tools/hongzhi_plugin.py`
- Impact:
  - `HONGZHI_CAPS` / `HONGZHI_INDEX` / `HONGZHI_HINTS` now append `json='...'`.
  - Legacy fields preserved (`path=`, version triplet, existing tokens).

3. Cross-command reuse hardening
- Files: `prompt-dsl-system/tools/hongzhi_plugin.py`
- Impact:
  - `profile` / `diff` default lookup now backtracks latest available discover `scan_graph.json`.
  - Command-local no-rescan counters now explicit (`java_files_indexed=0`, `bytes_read=0`) while source stats are preserved additively.

4. Regression gate expansion
- Files: `prompt-dsl-system/tools/golden_path_regression.sh`
- Impact:
  - Adds Phase32 with 6 checks.

## Contract Compatibility
- Additive only.
- Existing machine lines and capability schema keys are retained.

## Risk Surface
- Medium: machine-line parser interactions due new `json='...'` token.
- Mitigation: existing `path=` retained; Phase29 explain parser updated; rollback env gate added (`HONGZHI_MACHINE_JSON_ENABLE=0`).
