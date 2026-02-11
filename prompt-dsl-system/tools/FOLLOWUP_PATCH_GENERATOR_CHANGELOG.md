# FOLLOWUP_PATCH_GENERATOR Changelog

Generated at: 2026-02-10 (local)

## 新增/修改文件清单
- Added `prompt-dsl-system/tools/followup_patch_generator.py`
- Modified `prompt-dsl-system/tools/pipeline_runner.py`
- Modified `prompt-dsl-system/tools/run.sh`
- Modified `prompt-dsl-system/tools/risk_gate.py`
- Modified `prompt-dsl-system/tools/README.md`
- Added `prompt-dsl-system/tools/FOLLOWUP_PATCH_GENERATOR_TEST_NOTES.md`

## 置信度规则（保守）
- 仅自动处理高置信度替换：
  - `A_full_path`：完整旧路径字符串替换（含边界检查）。
  - `B_frontend_*`：前端静态资源上下文（`src/href/require/import`）目录替换。
  - `C_java_fqcn`：Java/XML 明确上下文（`import/class/mapper/...`）FQCN 替换。
- 明确禁止自动替换：
  - basename-only 命中
  - SQL 语义级替换（表/字段）
  - 二进制文件

## 默认安全策略
- 默认 `--mode plan`：只生成计划，不改文件。
- 无论 plan/apply 均先生成：
  - `followup_patch_plan.json`
  - `followup_patch_plan.md`
  - `followup_patch.diff`
- 仅当满足以下条件才真正 apply：
  - `--mode apply`
  - `--yes`
  - `--dry-run false`
  - 通过 `risk_gate` ACK（支持 `--ack` / `--ack-file` / `--ack-latest`）

## 风险闸门增强
- `risk_gate.py` 新增可选输入：
  - `--scan-report`
  - `--patch-plan`
- token reason hash 绑定扫描/补丁上下文摘要（去除易变字段后计算 digest），提升审计与复用安全性。

## 回滚方式
- Git:
  - `git restore <file>` 或 `git checkout -- <file>`（按团队策略）
- SVN:
  - `svn revert <file>`
- 若仅需撤销本次补丁：
  - 使用 `followup_patch.diff` 生成反向补丁，或按 `followup_patch_plan.json` 手工回退。

