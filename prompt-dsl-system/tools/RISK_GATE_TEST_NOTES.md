# RISK_GATE_TEST_NOTES

## 环境
- 日期：2026-02-10
- 仓库：`/Users/dwight/Downloads/【洪智科技】本地存档/beyond-dev-ai-kit`
- 说明：本仓库无 `.git/.svn`，guard 在 `unsupported_vcs` 模式下运行；HIGH 风险主要通过 loop 历史与合成报告触发。

## 用例 1：触发 HIGH 并阻断（exit 4）
- 命令：
  - `./prompt-dsl-system/tools/run.sh run -r . -m prompt-dsl-system --pipeline prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md --context-id ctx-risk-block --trace-id trace-risk-high --loop-window 6`
- 预期：
  - risk gate 阻断，退出码 `4`
  - 生成 `RISK_GATE_TOKEN.txt` 与 `risk_gate_report.json`
- 实际：
  - 退出码：`4`
  - stderr 含 `blocked before run plan: overall_risk=HIGH`
  - token/report 文件已生成。

## 用例 2：带 ACK 继续通过
- 命令：
  - 第一步（签发 token）：
    - `./prompt-dsl-system/tools/run.sh run ... --risk-threshold MEDIUM`（无 ACK，阻断签发）
  - 第二步（带 ACK）：
    - `./prompt-dsl-system/tools/run.sh run ... --risk-threshold MEDIUM --ack <TOKEN>`
- 预期：
  - 第二步通过，`risk_gate_report.json` 标记 `acked=true`
- 实际：
  - 第二步退出码：`0`
  - report：`acked=true`, `ack_valid=true`, `token.consumed=true`。

## 用例 3：阻断时 token 文件生成确认
- 检查文件：
  - `prompt-dsl-system/tools/RISK_GATE_TOKEN.txt`
- 预期字段：
  - `TOKEN`
  - `RISK`
  - `EXPIRES_AT`
  - `REASONS`
  - `NEXT_CMD_EXAMPLE`
- 实际：字段齐全。

## 用例 4：token 过期 / 上下文变化导致无效并重新签发

### 4.1 过期失效（ttl=0）
- 命令：
  - `python3 prompt-dsl-system/tools/risk_gate.py ... --ttl-minutes 0`（先签发）
  - `sleep 1` 后带旧 token 再 check
- 实测：
  - 首次：exit `4`（签发）
  - 再次：exit `4`（旧 token 无效，重新签发）

### 4.2 上下文变化失效（reason_hash 变化）
- 方法：签发后修改 loop trigger（例如 `A_file_set_loop -> B_boundary_probing`），再用旧 token check。
- 实测：exit `4`，重新签发 token。

## 结论
- risk_gate 已满足：
  - 高风险必须 ACK
  - 默认阻断退出码 `4`
  - token 具备 TTL 与上下文绑定（reason_hash）
  - ACK 通过后一次性消费（不可重复使用）
