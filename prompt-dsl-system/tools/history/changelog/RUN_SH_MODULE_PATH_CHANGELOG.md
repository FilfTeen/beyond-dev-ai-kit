# RUN_SH_MODULE_PATH_CHANGELOG

## Modified files
- `prompt-dsl-system/tools/run.sh`
- `prompt-dsl-system/tools/pipeline_runner.py`
- `prompt-dsl-system/tools/README.md`
- `prompt-dsl-system/tools/path_diff_guard.py` (new)
- `prompt-dsl-system/tools/guardrails.yaml` (new)
- `prompt-dsl-system/tools/RUN_SH_MODULE_PATH_TEST_NOTES.md` (new)

## New CLI argument support
- `pipeline_runner.py` now accepts `--module-path` for `list|validate|run`.
- `run.sh` now preserves and normalizes user-provided `--module-path` and validates directory existence.

## Guard priority
- Effective module path selection order is now:
  1. `cli` (`--module-path`)
  2. `pipeline` (explicit module_path in pipeline)
  3. `derived` (common prefix from step module_path values)
  4. `none`

## Behavior changes
- `run.sh` prints normalized module path when provided:
  - `[hongzhi] module_path=<normalized_path>`
- `pipeline_runner.py` writes scope metadata:
  - `validate_report.json`: `scope.effective_module_path`, `scope.module_path_source`
  - `run_plan.yaml`: `run.effective_module_path`, `run.module_path_source`
- validate/run now call Path Diff Guard before core logic and fail-fast on violations.
