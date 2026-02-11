# FOLLOWUP_VERIFIER_CHANGELOG

## 新增文件
- `prompt-dsl-system/tools/followup_verifier.py`
- `prompt-dsl-system/tools/FOLLOWUP_VERIFIER_TEST_NOTES.md`
- `prompt-dsl-system/tools/FOLLOWUP_VERIFIER_CHANGELOG.md`

## 修改文件
- `prompt-dsl-system/tools/pipeline_runner.py`
  - 新增子命令 `verify-followup-fixes`
  - 增加 `run_followup_verifier(...)` 调用封装
- `prompt-dsl-system/tools/run.sh`
  - 新增 `verify-followup-fixes` 子命令透传
- `prompt-dsl-system/tools/README.md`
  - 新增“verify-followup-fixes（残留引用验收）”章节与示例命令
- `prompt-dsl-system/tools/move_conflict_resolver.py`（推荐流程提示）
  - apply 成功后提示执行 verify-followup-fixes
- `prompt-dsl-system/tools/followup_patch_generator.py`（推荐流程提示）
  - apply 成功后提示执行 verify-followup-fixes

## 功能摘要
- 新增只读验收器：基于 `moves`（必填）+ `scan_report`/`patch_plan`（可选）构建旧引用 token 集并扫描仓库残留。
- 优先 `rg`，不可用时降级 `grep -R`。
- 产出：
  - `followup_verify_report.json`
  - `followup_verify_report.md`
- 支持三种模式参数：`post-move` / `post-patch` / `full`（默认 `full`）。

## 状态判定规则
- `PASS`: `hits_total == 0`
- `WARN`: `0 < hits_total <= 20`
- `FAIL`: `hits_total > 20`，或关键目录（`src/main/java` / `/pages/`）命中 `exact_paths`/`fqcn_hints`

## 推荐工作流
1. `resolve-move-conflicts` 或 `apply-followup-fixes` 完成后，运行 `verify-followup-fixes`
2. 若 `WARN/FAIL`，先修复残留再复跑 `verify-followup-fixes`
3. 验收 `PASS` 后继续 `validate` / `run`

## 回滚方式
- 本能力默认只读，不修改业务文件，无需回滚。
- 若后续配合其它 apply 子命令改动了文件，请使用现有版本控制命令回退（如 `git restore` / `svn revert`）。
