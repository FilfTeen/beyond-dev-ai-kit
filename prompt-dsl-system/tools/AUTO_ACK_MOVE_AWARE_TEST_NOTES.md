# AUTO_ACK_MOVE_AWARE Test Notes

## Scope
- area: `prompt-dsl-system/tools/**`
- goal: verify move-aware auto-ack policy (`outside_module` split into movable vs non-movable)

## Test Method
- Use synthetic reports under `prompt-dsl-system/tools/_tmp_auto_ack/` (temporary, cleaned after test).
- Generate `move_report.json` with `rollback_helper.py`.
- Evaluate `auto_ack_allowed` with `risk_gate.py --move-report ...`.

## Case 1: outside_module + module_path present + movable + high_risk=0
- Setup:
  - violation file: `prompt-dsl-system/tools/_tmp_auto_ack/other/src/main/java/com/acme/Demo.java`
  - module path: `prompt-dsl-system/tools/_tmp_auto_ack/moduleA`
  - no destination conflict
- Command sequence:
  1. `rollback_helper.py --emit move --only-violations true --module-path ...`
  2. `risk_gate.py --threshold HIGH --loop-report loop_high.json --move-report out1/move_report.json`
- Result:
  - `move_report.summary = {total:1, movable:1, non_movable:0, high_risk:0}`
  - `risk_gate_report.auto_ack_allowed = true`
  - `risk_gate` exits `4` (blocked as designed), but auto-retry eligibility is `allowed`.

## Case 2: outside_module + destination conflict (dst exists)
- Setup:
  - same source as case 1
  - pre-create destination: `moduleA/src/main/java/com/acme/Demo.java`
- Command sequence:
  1. `rollback_helper.py --emit move --only-violations true --module-path ...`
  2. `risk_gate.py --threshold HIGH --loop-report loop_high.json --move-report out2/move_report.json`
- Result:
  - `move_report.summary = {total:1, movable:0, non_movable:1, high_risk:1}`
  - blockers include destination conflict (`dst exists`)
  - `risk_gate_report.auto_ack_allowed = false`
  - `risk_gate_report.auto_ack_denied_reason = "some violations are not safely movable"`

## Case 3: missing module_path
- Setup:
  - violation type: `missing_module_path`
  - no `--module-path` passed to `rollback_helper.py`
- Command sequence:
  1. `rollback_helper.py --emit move --only-violations true` (without `-m`)
  2. `risk_gate.py --threshold HIGH --loop-report loop_high.json --move-report out3/move_report.json`
- Result:
  - `move_report.generated = false`, `generated_reason = "module_path unavailable"`
  - `move_report.summary = {total:1, movable:0, non_movable:1, high_risk:1}`
  - `risk_gate_report.auto_ack_allowed = false`
  - `risk_gate_report.auto_ack_denied_reason = "missing module_path requires manual intervention"`

