# APPLY_MOVE_CHANGELOG

## 新增/修改文件清单
- 修改：`prompt-dsl-system/tools/rollback_helper.py`
- 修改：`prompt-dsl-system/tools/pipeline_runner.py`
- 修改：`prompt-dsl-system/tools/run.sh`
- 修改：`prompt-dsl-system/tools/README.md`
- 新增：`prompt-dsl-system/tools/APPLY_MOVE_TEST_NOTES.md`
- 新增：`prompt-dsl-system/tools/APPLY_MOVE_CHANGELOG.md`

## 功能摘要
1. 新增 `apply-move` 子命令（`pipeline_runner.py` + `run.sh` 转发）：
   - 先做 advisory 预检并生成 `guard_report + move_plan + rollback_plan`
   - 若无违规：直接退出 `0`
   - 若有违规：进入 move 执行阶段（需要显式确认）
   - move 后自动复检，失败则提示 rollback，退出 `2`
2. `rollback_helper.py` 增强可执行入口：
   - 新增 `--apply-move`（等价于 `--emit move + --move-mode apply`）
   - 新增 `--plan-only`（强制只生成计划，不执行）
   - 新增 `move_apply_log.md`（记录执行命令、结果、冲突点）
3. `run.sh` 新增子命令：
   - 支持 `apply-move`
   - 保留 `-r/-m` 短参与参数透传
   - 输出观测行：`[hongzhi] cmd=apply-move repo_root=... module_path=...`

## apply-move 安全机制
- 默认不执行文件移动。
- 真正执行必须同时满足：
  - 进入 apply 语义（`apply-move` 调用链触发）
  - `--yes`
  - `--move-dry-run false`
  - `module-path` 可用（CLI 或 report）
- 任一条件不满足：
  - 仅生成计划
  - 输出确认提示
  - 退出码 `2`

## 迁移->复检闭环
1. `apply-move` 先执行 advisory 预检，刷新 `guard_report` 与计划。
2. 若决策 `fail` 且满足确认条件，则执行 move。
3. move 后自动 advisory 复检：
   - `pass`：输出 `move resolved violations`，建议继续 `validate/run`
   - `fail`：输出 `move did not fully resolve violations`，指向 `rollback_plan.sh` 并退出 `2`

## 失败时最短路径
1. 先查看并执行（按需）`move_plan.md / move_plan.sh` 的人工修正建议。
2. 若仍失败或存在冲突，使用 `rollback_plan.sh` 回滚。
3. 再运行：
   - `./prompt-dsl-system/tools/run.sh debug-guard -r . -m <MODULE_PATH>`
   - `./prompt-dsl-system/tools/run.sh validate -r . -m <MODULE_PATH>`
