# TRACE_BISECT Changelog

## 新增/修改文件清单
- 新增：`prompt-dsl-system/tools/trace_bisect_helper.py`
- 修改：`prompt-dsl-system/tools/pipeline_runner.py`
- 修改：`prompt-dsl-system/tools/run.sh`
- 修改：`prompt-dsl-system/tools/README.md`
- 新增：`prompt-dsl-system/tools/TRACE_BISECT_TEST_NOTES.md`
- 新增：`prompt-dsl-system/tools/TRACE_BISECT_CHANGELOG.md`

## auto-find-good 策略
- 当未传 `--good` 且 `--auto-find-good=true`：
  - 在 `trace_index.json` 中选择 `last_seen_at < bad.last_seen_at` 的候选。
  - 候选需满足：`latest_exit_code=0`（或历史命令存在 `run exit 0`）且 `verify_top` 命中 `--verify-top`（默认 `PASS`）。
  - 多候选取最近一条。
- 若找不到：仍生成计划，但标记 `good_missing=true` 并提示手工指定 `--good`。

## 步骤优先级（固定）
- P0：release/verify bypass 风险（最高优先）
- P1：verify FAIL 收敛
- P2：guard/边界违规
- P3：loop 反复改动
- P4：snapshot/deliveries 证据复盘

计划始终包含 S0（trace-diff 证据步骤），并自动控制总步数在 5~12（受 `--max-steps` 限制）。

## DRY_RUN 机制
- `bisect_plan.sh` 默认 `DRY_RUN=1`，仅回显命令不执行。
- 含占位符变量（`MODULE_PATH`/`PIPELINE_PATH`/`MOVES_JSON`/`SCAN_REPORT_JSON` 等）的步骤会先做变量检查，缺失则 `exit 2`。
- 仅在 `DRY_RUN=0` 时才执行命令。
