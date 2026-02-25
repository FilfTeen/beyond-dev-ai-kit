# AUTO_ACK_MOVE_AWARE ChangeLog

## Changed Files
- `prompt-dsl-system/tools/rollback_helper.py`
- `prompt-dsl-system/tools/risk_gate.py`
- `prompt-dsl-system/tools/pipeline_runner.py`
- `prompt-dsl-system/tools/run.sh`
- `prompt-dsl-system/tools/README.md`
- `prompt-dsl-system/tools/AUTO_ACK_MOVE_AWARE_TEST_NOTES.md`

## Strategy Summary
1. `move_report.json` upgraded to machine-readable mobility model:
- `module_path_normalized`
- `generated` / `generated_reason`
- `items[]` with `can_move`, `deny_reason`, `risk_flags`
- `summary.total/movable/non_movable/high_risk`

2. `risk_gate.py` is now move-aware:
- accepts `--move-report`
- computes:
  - `auto_ack_allowed`
  - `auto_ack_denied_reason`
  - `move_plan_available`
  - `move_plan_movable_ratio`
  - `move_plan_high_risk`
  - `move_plan_blockers`

3. `pipeline_runner.py` Gate-1/Gate-2 now pass `move_report.json` into `risk_gate.py` after debug-guard plan generation.

4. `run.sh` auto-retry is now policy-driven:
- on exit `4`, read `risk_gate_report.json`
- only auto-retry when `auto_ack_allowed=true`
- deny auto-retry with detailed blockers when policy says false

## Conservative Defaults
- `forbidden` violations: never auto-ack.
- `outside_module`: auto-ack only when move plan is generated, fully movable, and conflict-free.
- `missing_module_path`: never auto-ack.
- parse/report errors: fail closed (deny auto-ack).

## Rollback
If needed, revert these files to previous versions:
- `prompt-dsl-system/tools/rollback_helper.py`
- `prompt-dsl-system/tools/risk_gate.py`
- `prompt-dsl-system/tools/pipeline_runner.py`
- `prompt-dsl-system/tools/run.sh`
- `prompt-dsl-system/tools/README.md`

