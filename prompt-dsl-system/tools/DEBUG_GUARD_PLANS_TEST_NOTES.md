# DEBUG_GUARD_PLANS_TEST_NOTES

## 环境
- 日期：2026-02-10
- 主仓库：`/Users/dwight/Downloads/【洪智科技】本地存档/beyond-dev-ai-kit`
- 说明：主仓库当前无 `.git/.svn` 元数据，`path_diff_guard.py` 会进入 `unsupported_vcs` 非阻断模式；为验证 `decision=fail + advisory exit 0` 场景，补充了 `/tmp` 最小化 Git 仓库用例。

## 用例 1：有 `-m`，生成 guard + move + rollback
- 命令：
  - `./prompt-dsl-system/tools/run.sh debug-guard -r . -m prompt-dsl-system --output-dir prompt-dsl-system/tools --generate-plans true --plans both --only-violations true`
- 预期：
  - 生成 `guard_report.json`
  - 生成 `rollback_plan.md/.sh`
  - 生成 `move_plan.md`（若无可迁移文件可无 `.sh`）
- 实际：
  - 命令退出码：`0`
  - `guard_report.json`：`decision=pass`，`module_path_source=cli`，`module_path_normalized=prompt-dsl-system`
  - 已生成：`guard_report.json`、`rollback_plan.md/.sh`、`move_plan.md`（`move_plan.sh` 未生成，因无可迁移目标）

## 用例 2：无 `-m`，生成 guard + rollback；move 仅提示
- 命令：
  - `./prompt-dsl-system/tools/run.sh debug-guard -r . --output-dir prompt-dsl-system/tools --generate-plans true --plans both --only-violations true`
- 预期：
  - 生成 `guard_report.json`
  - 生成 `rollback_plan.md/.sh`
  - `move_plan.md` 提示需提供 `module-path`，且不生成 `move_plan.sh`
- 实际：
  - 命令退出码：`0`
  - `guard_report.json`：`decision=pass`，`module_path_source=none`，`module_path_normalized=null`
  - `move_plan.md` 含提示：`需提供 module-path 才能生成迁移目标路径。`
  - `move_plan.sh` 未生成（符合预期）

## 用例 3：有 violation 时，advisory 仍 exit 0 且 plans 生成
- 测试仓库：`/tmp/hongzhi_debug_guard_case`（最小化 Git 仓库，包含必需 marker 与 tools 脚本）
- 场景：
  - `module_path=module-a`
  - 实际改动文件：`module-b/src/outside.txt`（越界）
- 命令：
  - `./prompt-dsl-system/tools/run.sh debug-guard -r /tmp/hongzhi_debug_guard_case -m module-a --output-dir prompt-dsl-system/tools --generate-plans true --plans both --only-violations true`
- 预期：
  - 命令返回 `0`（advisory）
  - `guard_report.json` 为 `decision=fail`
  - 生成 `move_plan` 与 `rollback_plan`
- 实际：
  - 命令退出码：`0`
  - `guard_report.json`：`decision=fail`，`exit_code=0`，首条违规 `rule=out_of_allowed_scope`，`type=outside_module`
  - 已生成：`rollback_plan.md/.sh`、`move_plan.md/.sh`

## 结论
- `debug-guard` 已满足“预检即方案”：先 advisory guard，再自动生成 plan（move/rollback/both 可选）。
- 在 VCS 可用场景下，违规会进入 `decision=fail`，但 `debug-guard` 仍保持预检不阻断（退出码 `0`）。
