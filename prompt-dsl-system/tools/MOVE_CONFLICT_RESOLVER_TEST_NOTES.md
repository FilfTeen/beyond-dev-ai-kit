# MOVE_CONFLICT_RESOLVER Test Notes

Generated at: 2026-02-10 (local)

## Test Scope
- `apply-move` conflict branch (`dst exists`) in `pipeline_runner.py`
- `move_conflict_resolver.py` plan/apply flow
- Risk gate ACK requirement for conflict apply

## Environment Notes
- Main workspace is not a native git/svn root, so a disposable git sandbox was created under:
  - `prompt-dsl-system/tools/_tmp_move_conflict_repo`
- Sandbox only used to produce deterministic `git status` changed-files input for guard.

## Case 1: Create `dst exists` conflict fixture
- Command sketch:
```bash
mkdir -p prompt-dsl-system/tools/_tmp_move_conflict_repo/{module/src/main/java/com/t,other/src/main/java/com/t}
# create module target and outside-module source with same tail path
```
- Conflict condition:
  - source: `other/src/main/java/com/t/Conf.java`
  - mapped destination: `module/src/main/java/com/t/Conf.java` (already exists)
- Result:
  - `move_report.json` marks item with:
    - `can_move=false`
    - `deny_reason="dst exists"`
    - `risk_flags` contains `dst_exists`

## Case 2: `apply-move` detects conflict and emits conflict plans
- Command:
```bash
/usr/bin/python3 prompt-dsl-system/tools/pipeline_runner.py apply-move \
  --repo-root prompt-dsl-system/tools/_tmp_move_conflict_repo \
  --module-path module \
  --report prompt-dsl-system/tools/guard_report.json \
  --output-dir prompt-dsl-system/tools
```
- Expected:
  - detect conflict
  - generate `conflict_plan.md/json` and strategy scripts
  - stop with exit `2` for user decision
- Actual:
  - exit code `2`
  - stderr contains `Move conflicts detected`
  - generated:
    - `prompt-dsl-system/tools/conflict_plan.md`
    - `prompt-dsl-system/tools/conflict_plan_strategy_rename_suffix.sh`
    - `prompt-dsl-system/tools/conflict_plan_strategy_imports_bucket.sh`
    - `prompt-dsl-system/tools/conflict_plan_strategy_abort.sh`

## Case 3: Plan mode generates 3 strategy scripts
- Command:
```bash
./prompt-dsl-system/tools/run.sh resolve-move-conflicts -r . -m <MODULE_PATH> --strategy rename_suffix
```
- Expected:
  - plan only, no file move
  - all three strategy scripts generated
- Actual:
  - generated 3 scripts:
    - `conflict_plan_strategy_rename_suffix.sh`
    - `conflict_plan_strategy_imports_bucket.sh`
    - `conflict_plan_strategy_abort.sh`

## Case 4: Apply requires ACK (exit 4 -> token -> ack-latest passes)
- Command A (no ACK):
```bash
/usr/bin/python3 prompt-dsl-system/tools/pipeline_runner.py resolve-move-conflicts \
  --repo-root prompt-dsl-system/tools/_tmp_move_conflict_repo \
  --module-path module \
  --mode apply --strategy rename_suffix --yes --dry-run false --output-dir prompt-dsl-system/tools
```
- Expected A:
  - risk gate blocks with exit `4`
  - token file issued
- Actual A:
  - exit code `4`
  - token created under sandbox tools dir (`RISK_GATE_TOKEN.txt/json`)

- Command B (ACK latest):
```bash
/usr/bin/python3 prompt-dsl-system/tools/pipeline_runner.py resolve-move-conflicts \
  --repo-root prompt-dsl-system/tools/_tmp_move_conflict_repo \
  --module-path module \
  --mode apply --strategy rename_suffix --yes --dry-run false --output-dir prompt-dsl-system/tools --ack-latest
```
- Expected B:
  - pass risk gate
  - execute selected strategy script
  - write apply log
- Actual B:
  - exit code `0`
  - `conflict_apply_log.md` generated
  - source moved to suffix target `*.moved.<hash8>`

