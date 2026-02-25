# LOOP_DETECTOR_TEST_NOTES

## 环境
- 日期：2026-02-10
- 仓库：`/Users/dwight/Downloads/【洪智科技】本地存档/beyond-dev-ai-kit`
- 说明：本仓库无 `.git/.svn` 元数据，guard 处于 `unsupported_vcs` 非阻断模式；loop 检测由 `trace_history.jsonl` 驱动。

## 用例 1：如何模拟 3~6 次重复改动触发 LOOP_HIGH
步骤（可复现）：
1. 向 `prompt-dsl-system/tools/trace_history.jsonl` 追加 6 条同 `trace_id` 记录：
   - `pipeline_path` 相同
   - `effective_module_path` 相同
   - `changed_files_sample` 基本一致（Jaccard >= 0.7）
   - `guard_decision=fail` 或 `violations_count` 不下降
2. 执行：
   - `./prompt-dsl-system/tools/run.sh run -r . -m prompt-dsl-system --pipeline prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md --context-id ctx-loop-now --trace-id trace-loop-test --loop-window 6`
3. 观察：
   - `loop_diagnostics.json.level` 进入 `HIGH`
   - `triggers` 包含 `A_file_set_loop`（可能伴随 `B_boundary_probing`）

本次实测结果：
- 触发级别：`HIGH`
- 触发规则：`A_file_set_loop`, `B_boundary_probing`

## 用例 2：fail-on-loop 的 exit code 行为
命令：
- `./prompt-dsl-system/tools/run.sh run -r . -m prompt-dsl-system --pipeline prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md --context-id ctx-loop-now --trace-id trace-loop-test --fail-on-loop --loop-window 6`

预期：
- 当 loop level=HIGH 时阻断
- 退出码为 `--loop-exit-code`（默认 `3`）
- `trace_history.jsonl` 记录 `action=loop_blocked`

实测：
- 退出码：`3`
- 最后一条 trace 记录 action：`loop_blocked`

## 用例 3：默认不阻断，仅告警
命令：
- `./prompt-dsl-system/tools/run.sh run -r . -m prompt-dsl-system --pipeline prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md --context-id ctx-loop-now2 --trace-id trace-loop-test --loop-window 6`

预期：
- 仅告警不阻断
- 退出码 `0`
- `trace_history.jsonl` 记录 `action=loop_warned`

实测：
- 退出码：`0`
- 最后一条 trace 记录 action：`loop_warned`

## 用例 4：自动生成 debug-guard plans 确认
触发条件：loop level=MEDIUM/HIGH。

预期：
- 自动执行 advisory guard
- 生成/刷新：
  - `guard_report.json`
  - `move_plan.md` / `move_plan.sh`（如可生成）
  - `rollback_plan.md` / `rollback_plan.sh`

实测：
- 在 loop 告警与阻断场景下，上述文件均被自动生成或刷新。

## 结论
- anti-loop 已形成闭环：`run -> loop detect -> auto debug-guard plans -> warn/block`。
- 默认策略为“只警告不阻断”；开启 `--fail-on-loop` 后，`HIGH` 级会按配置退出码阻断。
