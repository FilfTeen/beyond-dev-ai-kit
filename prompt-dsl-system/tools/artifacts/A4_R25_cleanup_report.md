# A4_R25 Cleanup Report

## Cleanup Actions
- Kept all new outputs constrained to workspace/global-state roots.
- Added fixture only under `prompt-dsl-system/tools/_tmp_structure_cases/`.
- No writes introduced under target `repo_root` paths.

## Repo Hygiene
- No external dependencies added.
- No changes to unrelated top-level runtime scripts.
- Regression script expanded with isolated `_regression_tmp` resources and cleanup preserved.

## Residual Items
- Round25 introduces additional command path (`scan-graph`) and telemetry fields; downstream parsers should treat these as additive.
- Additional performance tuning is possible via deeper parser unification, but deferred to future rounds.
