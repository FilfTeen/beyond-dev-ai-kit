# DEBUG_GUARD_PLANS_CHANGELOG

## 变更目标
将 `debug-guard` 升级为“预检即方案”闭环：在 advisory 预检后自动生成 `guard_report + move_plan + rollback_plan`（默认仅生成，不执行）。

## 新增/修改文件
- 修改：`prompt-dsl-system/tools/pipeline_runner.py`
- 修改：`prompt-dsl-system/tools/rollback_helper.py`
- 修改：`prompt-dsl-system/tools/README.md`
- 新增：`prompt-dsl-system/tools/DEBUG_GUARD_PLANS_TEST_NOTES.md`
- 新增：`prompt-dsl-system/tools/DEBUG_GUARD_PLANS_CHANGELOG.md`

## 行为变化摘要
1. `debug-guard` 新增参数：
   - `--generate-plans`（默认 `true`）
   - `--plans move|rollback|both`（默认 `both`）
   - `--output-dir`（默认 `prompt-dsl-system/tools`）
   - `--only-violations`（默认 `true`）
   - `--module-path`（继续支持）
2. `debug-guard` 执行顺序固定为：
   - advisory guard（生成 `guard_report.json`）
   - 按 `--plans` 调用 `rollback_helper.py` 生成计划
3. `rollback_helper.py` 新增 `--emit both|move|rollback`：
   - `move`：仅生成 move 计划
   - `rollback`：仅生成 rollback 计划
   - `both`：两者都生成（默认）
4. 兼容策略：
   - `debug-guard` 仅在参数/路径错误时返回非 0；发现违规时也保持 exit `0`（advisory 语义）
   - `module-path` 缺失时仍生成 `move_plan.md` 提示，不生成 `move_plan.sh`

## 推荐工作流
1. 预检：
   - `./prompt-dsl-system/tools/run.sh debug-guard -r . -m <MODULE_PATH>`
2. 优先处理迁移建议：
   - 查看 `move_plan.md` / `move_plan.sh`（默认仅计划，不执行）
3. 再次校验：
   - `./prompt-dsl-system/tools/run.sh validate -r . -m <MODULE_PATH>`
4. 执行计划生成：
   - `./prompt-dsl-system/tools/run.sh run -r . -m <MODULE_PATH> --pipeline <PIPELINE>`
