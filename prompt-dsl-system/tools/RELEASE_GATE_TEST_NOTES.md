# RELEASE_GATE_TEST_NOTES

## Scope
- Repo: `beyond-dev-ai-kit`
- Tool layer only (`prompt-dsl-system/tools/**`)
- Objective: verify `followup_verify_report.json` drives release gate in `run/apply-move/apply-followup-fixes` (push commands).

## Case 1: 制造 verify FAIL，并验证 run 被 gate 阻断（exit 4）
1. 写入 FAIL 验收报告：
```bash
cat > prompt-dsl-system/tools/followup_verify_report.json <<'JSON'
{
  "generated_at": "2026-02-10T00:00:00+00:00",
  "summary": {
    "status": "FAIL",
    "hits_total": 3,
    "gate_recommended": true,
    "gate_reason": "verify status FAIL"
  }
}
JSON
```
2. 执行 run：
```bash
./prompt-dsl-system/tools/run.sh run -r . -m prompt-dsl-system \
  --pipeline prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md \
  --out prompt-dsl-system/tools/_tmp_release_gate_run_plan.yaml
```
3. 实际结果：`exit code = 4`，阻断成功。
4. 结构化报告确认：
- `overall_risk=HIGH`
- `verify_status=FAIL`
- `verify_gate_required=true`
- `auto_ack_allowed=false`

## Case 2: 生成 token 后，使用 --ack-latest 放行
```bash
./prompt-dsl-system/tools/run.sh run -r . -m prompt-dsl-system \
  --pipeline prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md \
  --out prompt-dsl-system/tools/_tmp_release_gate_run_plan.yaml \
  --ack-latest
```
实际结果：`exit code = 0`，放行成功，`risk_gate_report.json` 中 `acked=true`、`ack_valid=true`。

## Case 3: 清除残留后 verify PASS，run 不再拦截
1. 写入 PASS 验收报告：
```bash
cat > prompt-dsl-system/tools/followup_verify_report.json <<'JSON'
{
  "generated_at": "2026-02-10T00:10:00+00:00",
  "summary": {
    "status": "PASS",
    "hits_total": 0,
    "gate_recommended": false,
    "gate_reason": "verify status PASS"
  }
}
JSON
```
2. 执行 run（不带 ack）：
```bash
./prompt-dsl-system/tools/run.sh run -r . -m prompt-dsl-system \
  --pipeline prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md \
  --out prompt-dsl-system/tools/_tmp_release_gate_run_plan_pass.yaml
```
3. 实际结果：`exit code = 0`，`verify_gate_required=false`。

## Case 4: 临时关闭 verify-gate（排障开关）
在 verify=FAIL 下执行：
```bash
./prompt-dsl-system/tools/run.sh run -r . -m prompt-dsl-system \
  --pipeline prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md \
  --out prompt-dsl-system/tools/_tmp_release_gate_run_plan_nogate.yaml \
  --verify-gate false
```
实际结果：`exit code = 0`（默认策略仍建议保持 `--verify-gate true`）。
