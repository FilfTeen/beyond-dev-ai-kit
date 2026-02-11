# RELEASE_GATE_CHANGELOG

## 新增/修改文件清单
- 修改 `prompt-dsl-system/tools/followup_verifier.py`
- 修改 `prompt-dsl-system/tools/risk_gate.py`
- 修改 `prompt-dsl-system/tools/pipeline_runner.py`
- 修改 `prompt-dsl-system/tools/run.sh`
- 修改 `prompt-dsl-system/tools/README.md`
- 新增 `prompt-dsl-system/tools/RELEASE_GATE_TEST_NOTES.md`
- 新增 `prompt-dsl-system/tools/RELEASE_GATE_CHANGELOG.md`

## 默认门禁策略
- `verify-threshold=FAIL`（默认）
- `verify-gate=true`（默认）
- 推进型命令（`run` / `apply-move` / `apply-followup-fixes` 的 apply 场景）在执行前会走 release gate。
- 当 `followup_verify_report.json.summary.status=FAIL`：
  - `verify_gate_required=true`
  - `overall_risk` 至少提升到 `HIGH`
  - 若无 ACK，阻断并返回 `exit 4`

## risk_gate 输出增强
`risk_gate_report.json` 新增字段：
- `verify_status` (`PASS|WARN|FAIL|MISSING`)
- `verify_hits_total`
- `verify_gate_required`
- `verify_gate_reason`
- `verify_report`
- `verify_threshold`
- `verify_as_risk`
- `verify_required_for`
- `command_name`

## followup_verifier 输出增强
`followup_verify_report.json.summary` 新增：
- `gate_recommended`
- `gate_reason`

## 临时关闭 verify-gate（仅排障）
- 在相关命令增加：`--verify-gate false`
- 示例：
```bash
./prompt-dsl-system/tools/run.sh run -r . -m <MODULE_PATH> --pipeline <PIPELINE> --verify-gate false
```

## 回滚方式
- 仅工具链改动，无业务代码改动。
- 需要回滚时，恢复以下文件到上一版本即可：
  - `prompt-dsl-system/tools/followup_verifier.py`
  - `prompt-dsl-system/tools/risk_gate.py`
  - `prompt-dsl-system/tools/pipeline_runner.py`
  - `prompt-dsl-system/tools/run.sh`
  - `prompt-dsl-system/tools/README.md`
- 或直接使用版本控制回退到上一个可用提交。
