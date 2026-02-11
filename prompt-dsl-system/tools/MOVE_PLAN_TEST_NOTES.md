# MOVE_PLAN_TEST_NOTES

## Environment
- repo: `beyond-dev-ai-kit`
- runner wrapper: `prompt-dsl-system/tools/run.sh`
- python: `/usr/bin/python3`

## Case 1: module-path 存在时，生成 move_plan.sh
1. 先构造越界样本（advisory，不阻断）：
```bash
HONGZHI_GUARD_CHANGED_FILES="src/main/java/com/indihx/ownercommittee/service/Foo.java" \
./prompt-dsl-system/tools/run.sh debug-guard -r . -m prompt-dsl-system
```
2. 生成 rollback + move 计划：
```bash
./prompt-dsl-system/tools/run.sh rollback -r . -m prompt-dsl-system --report prompt-dsl-system/tools/guard_report.json --only-violations true
```
- 结果：
  - 生成 `prompt-dsl-system/tools/move_plan.md`
  - 生成 `prompt-dsl-system/tools/move_plan.sh`
  - 生成 `prompt-dsl-system/tools/move_report.json`

## Case 2: dst 冲突时脚本拒绝覆盖（安全检查验证）
- 使用生成脚本内容进行验证：
```bash
rg -n "destination exists|exit 2" prompt-dsl-system/tools/move_plan.sh
```
- 结果：脚本包含以下防护分支：
  - 目标已存在时输出 `[ERROR] destination exists: ...`
  - 立即 `exit 2`
- 说明：当前仓库仅含 `prompt-dsl-system`，未在仓库外创建测试文件以触发真实覆盖冲突；已通过脚本级安全分支检查确认“拒绝覆盖”机制存在且默认生效。

## Case 3: module-path 缺失时仅生成 move_plan.md（不生成 move_plan.sh）
```bash
./prompt-dsl-system/tools/run.sh validate -r .
./prompt-dsl-system/tools/run.sh rollback -r . --report prompt-dsl-system/tools/guard_report.json --only-violations true
```
- 结果：
  - `move_plan.md` 生成
  - `move_plan.sh` 不生成（且旧脚本会被清理）

## VCS 行为（git/svn/none）
- none（本仓库实测）：
  - `move_plan.sh` 使用 `mv`
  - `rollback_plan.sh` 输出手工回退提示/兜底命令
- git（未在本仓库实测）：
  - 预期 `move_plan.sh` 使用 `git mv` 保留历史
  - 验证方式：在 git 仓库中执行同命令并检查脚本内容与 `git status`
- svn（未在本仓库实测）：
  - 预期 `move_plan.sh` 使用 `svn mv` 保留历史
  - 验证方式：在 svn 工作副本中执行同命令并检查脚本内容与 `svn status`
