# BYPASS_DETECTOR_CHANGELOG

## 变更目标
将 verify gate 证据写入 trace，并对“verify FAIL 下反复推进/绕过”进行 LOOP_HIGH 检测；一旦命中，risk gate 自动禁用 auto-ack，仅允许人工 ACK。

## 新增/修改文件
- 修改：`prompt-dsl-system/tools/pipeline_runner.py`
- 修改：`prompt-dsl-system/tools/loop_detector.py`
- 修改：`prompt-dsl-system/tools/risk_gate.py`
- 新增：`prompt-dsl-system/tools/ack_notes.py`
- 修改：`prompt-dsl-system/tools/run.sh`
- 修改：`prompt-dsl-system/tools/README.md`
- 新增：`prompt-dsl-system/tools/BYPASS_DETECTOR_TEST_NOTES.md`
- 新增：`prompt-dsl-system/tools/BYPASS_DETECTOR_CHANGELOG.md`

## 规则摘要
1. trace_history 新增字段（推进型命令）：
- `command`
- `verify_status`
- `verify_hits_total`
- `verify_gate_required`
- `verify_gate_triggered`
- `ack_used`
- `blocked_by`
- `exit_code`

2. loop detector 新增最高优先级规则：`release_gate_bypass_attempt`
- 窗口内（默认 6）命中 >=2 次：
  - command ∈ `run/apply-move/apply-followup-fixes`
  - verify_status=`FAIL`
  - verify_gate_required=`true`
  - 且 `(blocked_by != verify_gate) OR (ack_used != none)`
- 结果：`level=HIGH`，并输出 `evidence.recent_attempts[]`。

3. risk gate 联动
- 当 loop triggers 包含 `release_gate_bypass_attempt`：
  - `overall_risk >= HIGH`
  - `auto_ack_allowed=false`
  - `auto_ack_denied_reason="verification failed and repeated bypass attempts detected; manual ack required"`

4. ack-note 轻量审计
- 推进命令在 verify FAIL 且 ACK 使用场景下，可追加 `--ack-note`。
- 落盘到：`prompt-dsl-system/tools/ack_notes.jsonl`。
- 未提供不阻断，仅提示建议补充。

## 默认不交互原则
- 不引入交互式输入。
- 默认行为保持可脚本化：仅在 gate 条件命中时阻断并输出下一步命令。

## 回滚方式
- 若要回退本次机制：
  1) 恢复 `pipeline_runner.py`、`loop_detector.py`、`risk_gate.py`、`run.sh`、`README.md` 到上一个稳定版本；
  2) 删除新增的 `ack_notes.py`、`BYPASS_DETECTOR_TEST_NOTES.md`、`BYPASS_DETECTOR_CHANGELOG.md`；
  3) 重新执行 `./prompt-dsl-system/tools/run.sh validate -r .` 确认体系恢复。

