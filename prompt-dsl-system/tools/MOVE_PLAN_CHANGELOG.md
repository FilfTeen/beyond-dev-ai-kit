# MOVE_PLAN_CHANGELOG

## 新增/修改文件
- modified: `prompt-dsl-system/tools/path_diff_guard.py`
- modified: `prompt-dsl-system/tools/pipeline_runner.py`
- modified: `prompt-dsl-system/tools/run.sh`
- modified: `prompt-dsl-system/tools/README.md`
- modified: `prompt-dsl-system/tools/guardrails.yaml`
- added: `prompt-dsl-system/tools/rollback_helper.py`
- added: `prompt-dsl-system/tools/MOVE_PLAN_TEST_NOTES.md`

## 功能摘要
1. Guard 报告增强
- 新增 `module_path_normalized`
- 新增 `effective_allowlist_prefixes`
- 每条 violation 新增 `type`：`forbidden|outside_module|missing_module_path`

2. rollback_helper 增强（核心）
- 在生成 `rollback_plan` 的同时生成 `move_plan`
- 支持参数：
  - `--module-path`
  - `--move-mode suggest|apply`（默认 suggest）
  - `--move-output-dir`
  - `--move-dry-run`（默认 true）
  - `--prefer-preserve-structure`（默认 true）
  - `--yes`（apply + 非 dry-run 必需）
- 产物：
  - `rollback_plan.md/.sh/.json`
  - `move_plan.md`、`move_plan.sh`（条件生成）、`move_report.json`

3. runner/run.sh 提示升级
- guard fail-fast 时，`pipeline_runner.py` stderr 追加 move-plan 推荐命令
- `run.sh` 新增 `rollback` 子命令并透传 `-m/--module-path`

## 安全机制
- 默认只生成计划，不执行迁移（`move-mode=suggest` + `move-dry-run=true`）
- `apply` 仅在 `--move-dry-run=false --yes` 时执行
- 迁移脚本默认包含：
  - 源文件存在检查
  - 目标存在冲突检查（冲突即 `exit 2`）
  - 按 VCS 选择 `git mv` / `svn mv` / `mv`
- 当 module-path 缺失时，不生成 `move_plan.sh`，仅输出说明和补充动作

## 推荐工作流（move 优先，rollback 兜底）
1. 先预检：
```bash
./prompt-dsl-system/tools/run.sh debug-guard -r . -m <MODULE_PATH>
```
2. 生成计划（默认不执行）：
```bash
./prompt-dsl-system/tools/run.sh rollback -r . -m <MODULE_PATH> --report prompt-dsl-system/tools/guard_report.json --only-violations true
```
3. 审核 `move_plan.md/move_report.json`，必要时再执行 `move_plan.sh` 或 `rollback_plan.sh`。
