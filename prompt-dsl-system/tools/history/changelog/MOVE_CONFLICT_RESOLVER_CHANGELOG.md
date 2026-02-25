# MOVE_CONFLICT_RESOLVER Changelog

Generated at: 2026-02-10 (local)

## Added / Modified Files
- Added `prompt-dsl-system/tools/move_conflict_resolver.py`
- Modified `prompt-dsl-system/tools/rollback_helper.py`
- Modified `prompt-dsl-system/tools/pipeline_runner.py`
- Modified `prompt-dsl-system/tools/run.sh`
- Modified `prompt-dsl-system/tools/README.md`
- Added `prompt-dsl-system/tools/MOVE_CONFLICT_RESOLVER_TEST_NOTES.md`

## Functional Summary
- Added conflict resolver for `dst exists` move-plan collisions with 3 deterministic strategies:
  - `rename_suffix`
  - `imports_bucket`
  - `abort`
- `apply-move` now branches on conflict:
  - auto-generate `conflict_plan.*`
  - stop and require explicit strategy selection (`exit 2`)
- Added `resolve-move-conflicts` command path in runner/run wrapper.
- Apply execution is still safe-by-default:
  - default mode is `plan`
  - real execution requires `--mode apply --yes --dry-run false`
  - conflict apply is risk-gated and requires valid ACK token.

## Safety Mechanisms
- No overwrite policy for conflict execution:
  - strategy scripts validate destination existence and fail fast on conflict.
- Risk gate hard-check before conflict apply:
  - no valid ACK -> block with `exit 4` and issue token.
- Shell command generation now uses shell-safe quoting (`shlex.quote`) to avoid path encoding failures.

## Rollback / Recovery
- Recommended path when conflict strategy does not fully resolve:
  1. Review `conflict_apply_log.md`
  2. Run `./prompt-dsl-system/tools/run.sh debug-guard -r . -m <MODULE_PATH>`
  3. If still failing, execute generated rollback plan (`rollback_plan.sh`) or perform manual conflict merge.

