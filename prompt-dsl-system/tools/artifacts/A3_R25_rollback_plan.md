# A3_R25 Rollback Plan

## Objective
Revert Round25 Unified Scan Graph changes with minimal blast radius.

## Rollback Steps
1. Remove new module:
- `prompt-dsl-system/tools/scan_graph.py`

2. Revert plugin integration:
- `prompt-dsl-system/tools/hongzhi_plugin.py`
  - remove scan_graph imports/helpers
  - remove `scan-graph` subcommand
  - remove `--scan-graph`/`--old-scan-graph`/`--new-scan-graph` flags
  - remove strict mismatch exit=25 logic
  - restore pre-R25 discover/profile/diff scan path

3. Revert tool-level reuse flags:
- `prompt-dsl-system/tools/module_profile_scanner.py` (`--scan-graph` path)
- `prompt-dsl-system/tools/cross_project_structure_diff.py` (`--old-scan-graph`/`--new-scan-graph` path)

4. Revert regression additions:
- `prompt-dsl-system/tools/golden_path_regression.sh`
  - remove Phase31 block
  - remove `CASE9` fixture reference

5. Remove Round25 fixture:
- `prompt-dsl-system/tools/_tmp_structure_cases/case7_scan_graph_weird_annotations/`

6. Revert docs/baselines:
- `prompt-dsl-system/tools/PLUGIN_RUNNER.md`
- `prompt-dsl-system/00_conventions/FACT_BASELINE.md`
- `prompt-dsl-system/00_conventions/COMPLIANCE_MATRIX.md`

## Verification After Rollback
- Run:
  - `./prompt-dsl-system/tools/run.sh validate --repo-root .`
  - `HONGZHI_VALIDATE_STRICT=1 ./prompt-dsl-system/tools/run.sh validate --repo-root .`
  - `bash prompt-dsl-system/tools/golden_path_regression.sh --repo-root .`
- Expect baseline to return to pre-R25 check count and pass state.
