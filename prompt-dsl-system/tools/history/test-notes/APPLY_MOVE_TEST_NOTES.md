# APPLY_MOVE_TEST_NOTES

## 环境
- 日期：2026-02-10
- 主仓库：`/Users/dwight/Downloads/【洪智科技】本地存档/beyond-dev-ai-kit`
- 说明：主仓库无 `.git/.svn` 元数据，因此“有违规”场景在 `/tmp` 最小化 Git 仓库验证。

## 用例 1：无违规 => `apply-move` 退出 0，不移动
- 命令：
  - `./prompt-dsl-system/tools/run.sh apply-move -r . -m prompt-dsl-system --output-dir prompt-dsl-system/tools`
- 预期：
  - 输出 `no violations, nothing to move`
  - 退出码 `0`
- 实际：
  - 退出码 `0`
  - 输出符合预期，未执行文件移动。

## 用例 2：有违规但未确认（缺 `--yes` / `--move-dry-run=true`）=> 不移动，退出 2
- 测试仓库：`/tmp/hongzhi_apply_move_case2c`
- 场景：
  - `module_path=module-a`
  - 违规变更：`module-b/src/outside.txt`（outside module）
- 命令：
  - `./prompt-dsl-system/tools/run.sh apply-move -r /tmp/hongzhi_apply_move_case2c -m module-a --output-dir prompt-dsl-system/tools --only-violations true`
- 预期：
  - 不执行移动
  - 退出码 `2`
  - 生成 `move_plan` 与 `rollback_plan`
- 实际：
  - 退出码 `2`
  - `source_exists=True`（源文件未移动）
  - `move_plan.md`、`rollback_plan.md`、`move_apply_log.md` 已生成。

## 用例 3：有违规且确认执行 => 移动成功，复检 pass，退出 0
- 测试仓库：`/tmp/hongzhi_apply_move_case3b`
- 场景：
  - `module_path=module-a`
  - 违规变更：`module-b/src/outside.txt`
- 命令：
  - `./prompt-dsl-system/tools/run.sh apply-move -r /tmp/hongzhi_apply_move_case3b -m module-a --output-dir prompt-dsl-system/tools --only-violations true --yes --move-dry-run false`
- 预期：
  - 执行移动
  - 复检通过
  - 退出码 `0`
- 实际：
  - 退出码 `0`
  - `module-b/src/outside.txt` 已移除，目标文件落在 `module-a/_imports/module-b__src__outside.txt`
  - 复检 `guard_report.decision=pass`
  - `move_apply_log.md` 已生成。

## 用例 4：移动后仍违规 => 复检 fail，指向 rollback_plan，退出 2
- 测试仓库：`/tmp/hongzhi_apply_move_case4`
- 场景：
  - 两类违规同时存在：
    - `module-b/src/outside.txt`（可迁移）
    - `prompt-dsl-system/util/forbidden.txt`（forbidden pattern，迁移后仍可触发违规）
- 命令：
  - `./prompt-dsl-system/tools/run.sh apply-move -r /tmp/hongzhi_apply_move_case4 -m module-a --output-dir prompt-dsl-system/tools --only-violations true --yes --move-dry-run false`
- 预期：
  - 执行迁移后仍违规
  - 输出 `move did not fully resolve violations`
  - 指向 `rollback_plan.sh`
  - 退出码 `2`
- 实际：
  - 退出码 `2`
  - 可迁移文件已移动到 `module-a/_imports/...`
  - `guard_report.decision=fail`（剩余 forbidden 违规）
  - 输出包含 `use rollback plan: prompt-dsl-system/tools/rollback_plan.sh`。

## 结论
- `apply-move` 已满足闭环：预检 -> 迁移（需确认）-> 复检。
- 安全默认生效：未显式确认不执行任何移动。
- 复检失败时会保留并刷新 rollback 方案，便于快速兜底。
