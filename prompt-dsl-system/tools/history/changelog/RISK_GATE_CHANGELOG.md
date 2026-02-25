# RISK_GATE_CHANGELOG

## 新增/修改文件清单
- 新增：`prompt-dsl-system/tools/risk_gate.py`
- 修改：`prompt-dsl-system/tools/pipeline_runner.py`
- 修改：`prompt-dsl-system/tools/run.sh`
- 修改：`prompt-dsl-system/tools/README.md`
- 新增：`prompt-dsl-system/tools/RISK_GATE_TEST_NOTES.md`
- 新增：`prompt-dsl-system/tools/RISK_GATE_CHANGELOG.md`

## 默认策略
- `run` 默认开启 risk gate（`--risk-gate true`）。
- Gate-1：run plan 生成前触发；高风险阻断并签发 token。
- Gate-2：run plan + loop 检测后触发；用于拦截后置高风险（尤其 loop 高风险场景）。
- 阈值默认 `HIGH`（可改 `--risk-threshold`）。

## 退出码说明
- risk gate 阻断默认退出码：`4`（可用 `--risk-exit-code` 覆盖）。
- guard 阻断仍保持 `2`。
- loop 强制阻断（`--fail-on-loop`）仍保持默认 `3`。

## 核心机制
- 风险聚合：`overall_risk = max(guard_risk, loop_risk)`。
- token 绑定：`repo_root + overall_risk + reason_hash + expires_at`。
- token 一次性：成功 ACK 后标记 `consumed=true`。
- 上下文变化（reason_hash 变化）/过期 token 自动失效并重新签发。

## 回滚方式
1. 临时关闭 risk gate（仅排障时）：
   - `--risk-gate false` 或 `--no-risk-gate`
2. 恢复旧行为（代码级）：
   - 回退 `pipeline_runner.py` 中 gate 调用段
   - 保留 `risk_gate.py` 但不在 `run` 中调用
3. 继续按安全流程：
   - `debug-guard -> apply-move -> validate -> run`
