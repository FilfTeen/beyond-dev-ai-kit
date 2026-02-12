# Health Runbook
- Generated at: 2026-02-12T16:20:06+08:00
- Mode: safe
- Repo root: /Users/dwight/Downloads/【洪智科技】本地存档/beyond-dev-ai-kit

## Fill-in Guide (replace placeholders)
- <MODULE_PATH>: 模块边界目录（绝对路径或相对 REPO_ROOT）。
  - Example: `prompt-dsl-system`
- <PIPELINE_PATH>: 目标 pipeline markdown 路径。
  - Example: `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md`
- <MOVES_JSON>: move mapping / move report 路径（verify-followup-fixes 输入）。
  - Example: `prompt-dsl-system/tools/moves_mapping_rename_suffix.json`
- <SCAN_REPORT_JSON>: followup 扫描报告路径（apply-followup-fixes 输入）。
  - Example: `prompt-dsl-system/tools/followup_scan_report_rename_suffix.json`
- <REPO_ROOT>: 仓库根路径，通常用 '.'。
  - Example: `.`

## Recommended Path (Shortest)
### Step 1 — Verify Residual References
- Purpose: 先把 verify FAIL 收敛到 PASS，终止 bypass 风险升级。
```bash
./prompt-dsl-system/tools/run.sh verify-followup-fixes -r "${REPO_ROOT}" --moves "${MOVES_JSON}"
```
- Expected output: 生成/更新 followup_verify_report.json，目标 status=PASS。
- If blocked: 先确认 MOVES_JSON 正确；若 risk gate 阻断，查看 prompt-dsl-system/tools/RISK_GATE_TOKEN.json，然后手动重试并追加 --ack-latest（必要时追加 --ack-note）。

### Step 2 — Run Plan (No ACK Auto)
- Purpose: 仅做计划生成，验证当前是否还能无风险推进。
```bash
./prompt-dsl-system/tools/run.sh run -r "${REPO_ROOT}" -m "${MODULE_PATH}" --pipeline "${PIPELINE_PATH}"
```
- Expected output: 生成 run_plan.yaml 或被 gate 阻断并给出 token。
- If blocked: 不要直接强推；先把 verify FAIL 修复到 PASS 后再考虑 ACK。

### Step 3 — ACK Note Guidance
- Purpose: 如确需临时放行，先记录人工理由保证审计可追溯。
```bash
# (no direct command; manual decision point)
```
- Expected output: 建议命令示例：... --ack-latest --ack-note "<reason>"
- If blocked: 仅在业务窗口紧急且影响已评估时使用。

### Step 4 — Verify Until PASS
- Purpose: 持续验证残留引用，直到 verify 报告为 PASS。
```bash
./prompt-dsl-system/tools/run.sh verify-followup-fixes -r "${REPO_ROOT}" --moves "${MOVES_JSON}"
```
- Expected output: followup_verify_report.json 状态收敛到 PASS。
- If blocked: 若报告 FAIL/WARN，继续下一步补丁 plan。

### Step 5 — Generate Follow-up Patch Plan
- Purpose: 只生成补丁计划，不直接改文件。
```bash
./prompt-dsl-system/tools/run.sh apply-followup-fixes -r "${REPO_ROOT}" --scan-report "${SCAN_REPORT_JSON}" --mode plan
```
- Expected output: 生成 followup_patch_plan.* 与 followup_patch.diff。
- If blocked: 修正 SCAN_REPORT_JSON 路径后重试。

### Step 6 — Re-Verify
- Purpose: 再次验证补丁计划后的残留状态。
```bash
./prompt-dsl-system/tools/run.sh verify-followup-fixes -r "${REPO_ROOT}" --moves "${MOVES_JSON}"
```
- Expected output: 目标 status=PASS；FAIL 则回到补丁 plan 循环。
- If blocked: 持续 FAIL 时先做 debug-guard + move plan 收敛边界问题。
