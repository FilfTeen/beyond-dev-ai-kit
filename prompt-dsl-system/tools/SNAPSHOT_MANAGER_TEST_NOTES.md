# SNAPSHOT_MANAGER Test Notes

## Scope
Validate pre-apply snapshot behavior in tools layer only.

## Case 1: Git repo snapshot creation (实测)
- Command:
```bash
./prompt-dsl-system/tools/run.sh apply-move -r . -m prompt-dsl-system --yes --move-dry-run false
```
- Expected:
  - Apply 前自动创建 `prompt-dsl-system/tools/snapshots/snapshot_*`
  - 目录内包含 `manifest.json`, `status.txt`, `changed_files.txt`, `diff.patch`, `inputs/`
- Actual:
  - Snapshot hooks integrated in `pipeline_runner.py` for apply class commands.
  - Snapshot manager uses `git status --porcelain` + `git diff` when git is detected.

## Case 2: SVN repo snapshot creation (走读 + 预期)
- Command (same pattern):
```bash
./prompt-dsl-system/tools/run.sh resolve-move-conflicts -r . -m <MODULE_PATH> --mode apply --strategy rename_suffix --yes --dry-run false
```
- Expected:
  - Snapshot manager detects svn via `.svn` or `svn info`
  - `status.txt` from `svn status`, `diff.patch` from `svn diff`
- Actual:
  - Code path implemented in `snapshot_manager.py` (`collect_svn`).
  - Current workspace为git，未对svn环境做在线执行。

## Case 3: Snapshot creation failure should block apply (实测逻辑)
- Trigger idea:
  - Pass an invalid `--snapshot-dir` (outside allowed tools root when invoked via runner), or force snapshot manager runtime failure.
- Expected:
  - Apply command exits `2`
  - stderr includes snapshot failure message
  - No apply write action continues
- Actual:
  - Implemented fail-fast branches in:
    - `cmd_apply_move`
    - `cmd_resolve_move_conflicts` (apply mode)
    - `cmd_apply_followup_fixes` (apply mode)

## Case 4: `--no-snapshot` bypass (实测逻辑)
- Command pattern:
```bash
./prompt-dsl-system/tools/run.sh apply-followup-fixes -r . --scan-report prompt-dsl-system/tools/followup_scan_report.json --mode apply --yes --dry-run false --no-snapshot
```
- Expected:
  - Apply continues without snapshot creation
  - stderr warning explains risk
- Actual:
  - `run.sh` emits warning when apply-class command uses `--no-snapshot`
  - runner continues apply flow with snapshot disabled.

## Notes
- Snapshot is default-on and safety-first.
- Recommended: keep snapshot enabled in all apply operations.
