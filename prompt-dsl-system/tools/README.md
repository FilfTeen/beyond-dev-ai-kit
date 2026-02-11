# Pipeline Runner Tools

## 用途
`pipeline_runner.py` 用于把 pipeline markdown 中的 YAML 调用块解析为可执行计划，并提供一致性校验。

能力范围：
- 读取 `prompt-dsl-system/05_skill_registry/skills.json`
- 读取 `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_*.md`
- 提取 step YAML（`skill` + `parameters`）
- 生成 `run_plan.yaml`
- 生成 `validate_report.json`

## 推荐解释器（稳定运行）
- 优先使用：`/usr/bin/python3`（Python 3.9+）。
- 本机环境中，`python.org Framework Python 3.14` 可能触发 `SIGKILL`（表现为 `zsh: killed`），不建议用于本仓库工具链。
- 推荐通过 `prompt-dsl-system/tools/run.sh` 统一调用，避免解释器漂移。

## 快速开始
在仓库根目录执行：

```bash
/usr/bin/python3 prompt-dsl-system/tools/pipeline_runner.py list --repo-root .
/usr/bin/python3 prompt-dsl-system/tools/pipeline_runner.py validate --repo-root .
/usr/bin/python3 prompt-dsl-system/tools/pipeline_runner.py run --repo-root . --pipeline prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md
```

或使用包装脚本：

```bash
./prompt-dsl-system/tools/run.sh list -r .
./prompt-dsl-system/tools/run.sh validate -r .
./prompt-dsl-system/tools/run.sh run -r . -m <MODULE_PATH> --pipeline prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md
./prompt-dsl-system/tools/run.sh resolve-move-conflicts -r . -m <MODULE_PATH> --strategy rename_suffix
./prompt-dsl-system/tools/run.sh scan-followup -r . --moves prompt-dsl-system/tools/move_report.json
./prompt-dsl-system/tools/run.sh apply-followup-fixes -r . --scan-report prompt-dsl-system/tools/followup_scan_report.json
./prompt-dsl-system/tools/run.sh verify-followup-fixes -r . --moves prompt-dsl-system/tools/moves_mapping_rename_suffix.json
./prompt-dsl-system/tools/run.sh snapshot-restore-guide -r . --snapshot prompt-dsl-system/tools/snapshots/<SNAPSHOT_DIR>
./prompt-dsl-system/tools/run.sh snapshot-prune --keep-last 30 --max-total-size-mb 2048
./prompt-dsl-system/tools/run.sh snapshot-index
./prompt-dsl-system/tools/run.sh snapshot-open --trace-id <TRACE_ID>
./prompt-dsl-system/tools/run.sh trace-index -r .
./prompt-dsl-system/tools/run.sh trace-open -r . --trace-id trace-c4d7
./prompt-dsl-system/tools/run.sh trace-diff -r . --a trace-c4d7 --b trace-xxxx
./prompt-dsl-system/tools/run.sh trace-bisect -r . --bad trace-xxxx
```

公司标准（推荐）：

```bash
./prompt-dsl-system/tools/run.sh validate -r .
./prompt-dsl-system/tools/run.sh run -r . -m <MODULE_PATH> --pipeline <PIPELINE>
./prompt-dsl-system/tools/run.sh rollback -r . -m <MODULE_PATH> --report prompt-dsl-system/tools/guard_report.json
```

说明：
- `run` 子命令默认强制要求 `-m/--module-path`（公司边界要求），避免跨模块误改。
- `validate` 的 `module-path` 可选；未提供时，guard 将只允许 `prompt-dsl-system/**` 变更。
- 可临时放宽 `run` 强制：`HONGZHI_ALLOW_RUN_WITHOUT_MODULE_PATH=1`（会打印风险警告）。
- `--module-path` 支持绝对路径或相对 `--repo-root`；`run.sh` 会先校验目录存在并规范化路径。
- Guard 优先级：`cli (--module-path) > pipeline > derived > none`。

## Policy Pack（统一策略包）
策略文件：
- 默认策略：`prompt-dsl-system/tools/policy.yaml`（人类可编辑）
- 机器镜像：`prompt-dsl-system/tools/policy.json`
- validate 产物：`prompt-dsl-system/tools/policy_effective.json`、`prompt-dsl-system/tools/policy_sources.json`

覆盖优先级（高到低）：
1. CLI 参数（`--policy-override key=value`）
2. 仓库覆盖文件（可选）：
   - `<repo_root>/.prompt-dsl-policy.yaml`
   - `<repo_root>/.prompt-dsl-policy.json`
3. `prompt-dsl-system/tools/policy.yaml`
4. 工具内建 defaults

`run.sh` 行为：
- 若未显式传 `--policy`，会自动注入 `prompt-dsl-system/tools/policy.yaml`（文件存在时）。
- 透传 `--policy` / `--policy-override` 给 `pipeline_runner.py` 及下游工具链。

示例：

```bash
./prompt-dsl-system/tools/run.sh validate -r . --policy-override health.window=30
./prompt-dsl-system/tools/run.sh validate -r . --policy-override prune.keep_last=50
./prompt-dsl-system/tools/run.sh run -r . -m <MODULE_PATH> --pipeline <PIPELINE> --policy-override gates.loop_gate.window=8
```

## 输出文件
- `prompt-dsl-system/tools/run_plan.yaml`：`run` 子命令生成的执行计划。
- `prompt-dsl-system/tools/validate_report.json`：`validate` 子命令生成的结构化校验报告。
- `prompt-dsl-system/tools/policy_effective.json`：`validate` 刷新的最终生效策略（合并后）。
- `prompt-dsl-system/tools/policy_sources.json`：`validate` 输出的策略来源清单（tools/repo/cli）。
- `prompt-dsl-system/tools/policy.json`：机器读取策略镜像（与 effective 同步刷新）。
- `prompt-dsl-system/tools/health_report.json` / `health_report.md`：`validate` 末尾自动生成的全局健康汇总（registry/pipelines/trace/risk/verify）。
- `prompt-dsl-system/tools/health_runbook.json` / `health_runbook.md` / `health_runbook.sh`：`validate` 末尾自动生成的最短收敛路径 runbook（默认 safe）。
- `prompt-dsl-system/tools/merged_integrity_report.json`：`merged_guard.py` 生成的 merged/batches 完整性报告。
- `prompt-dsl-system/tools/guard_report.json`：`path_diff_guard.py` 生成的路径越界检查报告。
- `prompt-dsl-system/tools/rollback_plan.md` / `rollback_plan.sh`：回滚建议计划与脚本（默认不执行）。
- `prompt-dsl-system/tools/move_plan.md` / `move_plan.sh`：越界文件迁移建议（推荐优先使用，默认不执行）。
- `prompt-dsl-system/tools/move_report.json`：结构化迁移映射报告。
- `prompt-dsl-system/tools/trace_history.jsonl`：run 轨迹账本（jsonl 逐行追加）。
- `prompt-dsl-system/tools/loop_diagnostics.json` / `loop_diagnostics.md`：anti-loop 诊断结果。
- `prompt-dsl-system/tools/RISK_GATE_TOKEN.txt`：高风险 ACK 一次性令牌文件。
- `prompt-dsl-system/tools/RISK_GATE_TOKEN.json`：高风险 ACK 结构化令牌（供 `--ack-latest/--ack-file` 使用）。
- `prompt-dsl-system/tools/risk_gate_report.json`：risk gate 结构化审计报告。
- `prompt-dsl-system/tools/snapshots/snapshot_*/`：apply 前自动快照（status/diff/inputs/manifest）。

## Health Report（validate 自动生成）
`validate` 成功结束后会自动调用 `health_reporter.py` 生成：
- `prompt-dsl-system/tools/health_report.md`
- `prompt-dsl-system/tools/health_report.json`

示例：

```bash
./prompt-dsl-system/tools/run.sh validate -r .
./prompt-dsl-system/tools/run.sh validate -r . --health-window 30
./prompt-dsl-system/tools/run.sh validate -r . --trace-history prompt-dsl-system/tools/trace_history.jsonl
```

可选关闭自动生成：

```bash
./prompt-dsl-system/tools/run.sh validate -r . --no-health-report
```

## Health Runbook（validate 自动生成）
`validate` 在生成 `health_report.*` 后会继续调用 `health_runbook_generator.py`，输出：
- `prompt-dsl-system/tools/health_runbook.md`
- `prompt-dsl-system/tools/health_runbook.sh`
- `prompt-dsl-system/tools/health_runbook.json`

示例：

```bash
./prompt-dsl-system/tools/run.sh validate -r . --runbook-mode safe
./prompt-dsl-system/tools/run.sh validate -r . --runbook-mode aggressive
./prompt-dsl-system/tools/run.sh validate -r . --no-health-runbook
```

使用方式：
1. 打开 `health_runbook.md`，先填写占位符：`<MODULE_PATH> <PIPELINE_PATH> <MOVES_JSON> <SCAN_REPORT_JSON>`。
2. 直接执行 `health_runbook.sh`（或复制 md 中命令分步执行）。
3. `safe` 模式默认只做只读/plan；不会自动附加 `--ack`，也不会做 destructive 执行。

如何阅读与如何行动（最短路径）：
1. 先看 `Build Integrity`：若 `Validate=FAIL`，先修 registry/pipeline 结构问题。
2. 再看 `Execution Signals`：若 `verify_status=FAIL` 或 `exit_code=4` 占比高，先收敛 verify/risk 触发点再推进。
3. 最后看 `Risk Triggers`：若出现 `release_gate_bypass_attempt`，先停止推进并修复残留，必要时补 `--ack-note`。

## Company Execution Profile（公司执行配置）
- 策略单一事实源：`prompt-dsl-system/company_profile.yaml`。
- `pipeline_runner.py` 在 `run/validate` 时会尝试读取该 profile：
  - `validate`：在 `validate_report.json` 的 `profile` 区块输出 `found/parsed/applied_possible/effective_defaults`。
  - `run`：在 `run_plan.yaml` 的 `run.profile` 区块输出 `path/applied/injected_defaults`。
- 注入规则（兼容模式）：
  - 仅在 step 参数缺失时注入：`schema_strategy` / `execution_tool` / `require_precheck_gate`。
  - 若用户显式提供参数，不会覆盖。
  - 若 profile 不存在或解析失败，不报错中断，只是不注入默认值。

示例命令：

```bash
./prompt-dsl-system/tools/run.sh validate -r .
./prompt-dsl-system/tools/run.sh run -r . -m prompt-dsl-system --pipeline prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_db_delivery_batch_and_runbook.md
```

## merged_guard（发布前闸门）
用于校验某个 trace 的 merged/batches 完整性，避免 merged 缺段或关键表缺失。

```bash
/usr/bin/python3 prompt-dsl-system/tools/merged_guard.py --trace-id trace-c4d7acea934f4bbbb5a8979a1de7051b
```

## ops_guard（公司作业边界闸门）
用于执行公司域边界检查：禁止路径、allowed-root 越界、循环风险信号（若无日志会提示“需用户提供执行日志”）。

标准命令模板（每次作业前/后都执行）：

```bash
/usr/bin/python3 prompt-dsl-system/tools/ops_guard.py --repo-root . --allowed-root <ALLOWED_MODULE_ROOT>
```

常见流程模板：

```bash
# pre-check
/usr/bin/python3 prompt-dsl-system/tools/ops_guard.py --repo-root . --allowed-root <ALLOWED_MODULE_ROOT>

# run pipeline
./prompt-dsl-system/tools/run.sh run --repo-root . --pipeline <PIPELINE_PATH>

# post-check
/usr/bin/python3 prompt-dsl-system/tools/ops_guard.py --repo-root . --allowed-root <ALLOWED_MODULE_ROOT>
```

## 约束
- 默认只生成计划与报告，不触发业务变更。
- 只有在显式 apply 且确认参数满足时，才会执行文件改动（并受 risk gate + snapshot 保护）。

## Path Diff Guard（validate/run 自动执行）
- 作用：阻断越界改动、防止污染公区目录、强制遵守模块边界。
- 默认禁止模式：`**/sys/**`, `**/error/**`, `**/util/**`, `**/vote/**`, `**/.git/**`, `**/target/**`, `**/node_modules/**`。
- 规则来源：`prompt-dsl-system/tools/guardrails.yaml`。
- 失败处理：validate/run 直接 fail-fast（exit 2），并提示查看 `guard_report.json`。

## Move Plan（推荐优先于回滚）
当 guard 阻断时，优先用“迁移计划”把越界文件迁回 `module_path`，避免直接回滚导致工作丢失。

示例：

```bash
./prompt-dsl-system/tools/run.sh rollback -r . -m <MODULE_PATH> --report prompt-dsl-system/tools/guard_report.json
# 查看 move_plan.md / move_plan.sh / move_report.json
```

说明：
- 默认仅生成计划，不执行移动。
- 若 `module_path` 缺失，仍会生成 `move_plan.md`，但不会生成 `move_plan.sh`。
- 需要执行迁移时，使用 `rollback_helper.py --move-mode apply --move-dry-run false --yes`。

## 预检即方案：debug-guard
用于在不阻断的前提下查看当前 guard 生效规则和潜在越界风险，并默认自动生成迁移/回滚方案（仅生成，不执行）。

```bash
./prompt-dsl-system/tools/run.sh debug-guard -r . -m <MODULE_PATH>
```

最推荐命令（预检即方案）：

```bash
./prompt-dsl-system/tools/run.sh debug-guard -r . -m <MODULE_PATH>
```

默认会生成：
- `prompt-dsl-system/tools/guard_report.json`
- `prompt-dsl-system/tools/move_plan.md` / `prompt-dsl-system/tools/move_plan.sh`（如可生成）
- `prompt-dsl-system/tools/rollback_plan.md` / `prompt-dsl-system/tools/rollback_plan.sh`

可选参数：
- `--generate-plans true|false`（默认 `true`）
- `--plans move|rollback|both`（默认 `both`）
- `--output-dir prompt-dsl-system/tools`（必须在 tools 下）
- `--only-violations true|false`（默认 `true`）

输出包括：
- forbidden patterns
- ignore patterns
- effective module path（repo 相对路径）
- allow path set（`prompt-dsl-system/**` + `module_path/**`）
- advisory 模式下生成的 `guard_report.json`
- advisory 预检不阻断（除参数/路径错误外，命令返回 0）

## apply-move（执行迁移并复检）
用于在 guard 发现越界后，按显式确认执行 move，并自动复检。

推荐流程：
1. `debug-guard` 预检并生成计划。
2. `apply-move` 执行迁移（需要显式确认）。
3. `validate` 再校验。
4. `run` 生成执行计划。

仅计划模式（默认安全）：

```bash
./prompt-dsl-system/tools/run.sh apply-move -r . -m <MODULE_PATH>
# 仅生成计划并提示如何确认执行
```

真正执行迁移：

```bash
./prompt-dsl-system/tools/run.sh apply-move -r . -m <MODULE_PATH> --yes --move-dry-run false
```

说明：
- `apply-move` 会先执行 advisory 预检并刷新 `guard_report + move_plan + rollback_plan`。
- 若无违规：直接输出 `no violations, nothing to move`，退出码 `0`。
- 若有违规且未显式确认（缺 `--yes` 或 `--move-dry-run=true`）：不移动任何文件，退出码 `2`。
- 若执行后复检仍失败：会刷新 rollback 方案并提示优先查看 `rollback_plan.sh`，退出码 `2`。

## Move 冲突处理（dst exists）三策略
当 `apply-move` 检测到 `dst exists` 冲突，会自动生成：
- `conflict_plan.md`
- `conflict_plan.json`
- `conflict_plan_strategy_rename_suffix.sh`
- `conflict_plan_strategy_imports_bucket.sh`
- `conflict_plan_strategy_abort.sh`
- `moves_mapping_rename_suffix.json` / `moves_mapping_imports_bucket.json` / `moves_mapping_abort.json`
- `followup_checklist_rename_suffix.md` / `followup_checklist_imports_bucket.md` / `followup_checklist_abort.md`
- `followup_scan_report_rename_suffix.json` / `followup_scan_report_imports_bucket.json` / `followup_scan_report_abort.json`

三策略说明：
- `rename_suffix`：移动到 `dst.moved.<hash8>`，不覆盖原目标文件。
- `imports_bucket`：移动到 `<module_path>/_imports_conflicts/...`，避免结构冲突。
- `abort`：不移动，要求人工处理冲突后再执行。

推荐流程：
1. `apply-move` 检测冲突并生成 `conflict_plan.md`。
2. 选择策略并先走 plan 模式。
3. 真正执行必须：`--mode apply --yes --dry-run false` 且通过 risk gate ACK。

示例：
```bash
./prompt-dsl-system/tools/run.sh resolve-move-conflicts -r . -m <MODULE_PATH> --strategy rename_suffix
./prompt-dsl-system/tools/run.sh resolve-move-conflicts -r . -m <MODULE_PATH> --strategy rename_suffix --mode apply --yes --dry-run false --ack-latest
```

## 引用修复清单（follow-up checklist）
`resolve-move-conflicts` 生成 `conflict_plan.*` 时，会自动附带三套“静态扫描候选清单”，用于定位可能需要调整的引用：
- `followup_checklist_rename_suffix.md`
- `followup_checklist_imports_bucket.md`
- `followup_checklist_abort.md`

说明：
- 仅基于静态字符串扫描（`rg` 优先，缺失时回退 `grep`），不做业务推断。
- 结果是候选项，必须人工确认后再修改。
- 每个 move 最多记录 `max_hits_per_move` 条命中（默认 50，超出会截断并在 report 标记）。

单独运行扫描：
```bash
./prompt-dsl-system/tools/run.sh scan-followup -r . --moves prompt-dsl-system/tools/move_report.json
./prompt-dsl-system/tools/run.sh scan-followup -r . --moves prompt-dsl-system/tools/conflict_plan.json --output-dir prompt-dsl-system/tools
```

## apply-followup-fixes（谨慎补丁模式）
用于从 `followup_scan_report*.json` 生成“高置信度替换补丁计划”。

默认安全行为：
- 只生成计划与 diff，不修改任何文件。
- 输出：
  - `followup_patch_plan.json`
  - `followup_patch_plan.md`
  - `followup_patch.diff`

高置信度自动替换仅包含：
- 完整旧路径字符串 -> 新路径（边界校验）
- 前端静态资源上下文（`src/href/require/import`）中的目录路径替换
- Java/XML 明确上下文（`import/class/mapper/...`）中的 FQCN 替换

默认禁止自动替换：
- basename-only 命中（如 `Foo.java`）
- SQL 语义级替换（表/字段）
- 二进制文件

计划模式（默认）：
```bash
./prompt-dsl-system/tools/run.sh apply-followup-fixes -r . \
  --scan-report prompt-dsl-system/tools/followup_scan_report_rename_suffix.json
```

真正 apply（必须显式确认 + risk gate ACK）：
```bash
./prompt-dsl-system/tools/run.sh apply-followup-fixes -r . \
  --scan-report prompt-dsl-system/tools/followup_scan_report_rename_suffix.json \
  --mode apply --yes --dry-run false --ack-latest
```

## Snapshot（apply 前自动回滚点）
以下真实写盘动作会在执行前自动创建 snapshot：
- `apply-move --yes --move-dry-run false`
- `resolve-move-conflicts --mode apply --yes --dry-run false`
- `apply-followup-fixes --mode apply --yes --dry-run false`

默认行为：
- 开启自动快照，输出目录：`prompt-dsl-system/tools/snapshots/`
- 若快照创建失败，命令会阻断（exit 2），避免“无回滚点写盘”
- trace 会记录 `snapshot_created/snapshot_path/snapshot_label`

可选参数：
- `--snapshot true|false`
- `--no-snapshot`（不推荐；会打印风险警告）
- `--snapshot-dir prompt-dsl-system/tools/snapshots`
- `--snapshot-label <LABEL>`

快照目录包含：
- `manifest.json` / `manifest.md`
- `vcs_detect.json`
- `status.txt` / `changed_files.txt`
- `diff.patch`（git/svn 可用时）
- `inputs/`（move/guard/risk/verify 等关键输入报告拷贝）
- `notes.md`

恢复指引（仅提示，不自动回滚）：
- git（全量）：`git reset --hard && git clean -fd`
- svn（全量）：`svn revert -R .`
- 部分文件：`git restore -- <path>` 或 `svn revert <path>`

## Snapshot Restore Guide
用于从已有 snapshot 目录生成恢复向导与回滚脚本（默认仅生成，不执行）。

选择 snapshot：
```bash
ls -1 prompt-dsl-system/tools/snapshots/
```

生成恢复脚本（默认 strict + dry-run）：
```bash
./prompt-dsl-system/tools/run.sh snapshot-restore-guide -r . \
  --snapshot prompt-dsl-system/tools/snapshots/<SNAPSHOT_DIR>
```

生成产物（默认在 `<snapshot>/restore/`）：
- `restore_guide.md`
- `restore_full.sh`
- `restore_files.sh`
- `restore_check.json`

执行策略：
- `restore_files.sh`：按 `changed_files.txt` 回滚，优先使用。
- `restore_full.sh`：全量回滚，风险更高。
- 两个脚本默认 `DRY_RUN=1`，不会执行破坏命令；仅在显式 `DRY_RUN=0` 时真正执行。

## Snapshot Prune（清理快照）
用于对 `prompt-dsl-system/tools/snapshots/` 执行可审计清理，默认 dry-run，仅输出计划。

示例（默认 dry-run）：
```bash
./prompt-dsl-system/tools/run.sh snapshot-prune --keep-last 30 --max-total-size-mb 2048
```

示例（显式执行删除）：
```bash
./prompt-dsl-system/tools/run.sh snapshot-prune --keep-last 30 --max-total-size-mb 2048 --apply
```

支持策略：
- 保留最近 N 个（按 `created_at`）
- 总大小上限（MB）
- 标签过滤：`--only-label` / `--exclude-label`
- 安全护栏：仅删除 `snapshot_*` 且存在 `manifest.json` 的目录；invalid entries 永不删除

输出：
- `prompt-dsl-system/tools/snapshot_prune_report.json`
- `prompt-dsl-system/tools/snapshot_prune_report.md`

注意：
- `--apply` 删除不可逆，建议先 dry-run 审核报告再执行。

## Snapshot Index / Open
用于索引和快速定位 snapshot，便于按 `trace_id/context_id/label/snapshot_id` 检索。

生成索引：
```bash
./prompt-dsl-system/tools/run.sh snapshot-index
```

按 trace 定位：
```bash
./prompt-dsl-system/tools/run.sh snapshot-open --trace-id trace-c4d7...
```

按 label 定位最新：
```bash
./prompt-dsl-system/tools/run.sh snapshot-open --label apply-followup-fixes --latest
```

输出文件：
- `prompt-dsl-system/tools/snapshot_index.json`
- `prompt-dsl-system/tools/snapshot_index.md`

`snapshot-open` 默认行为：
- 多匹配时默认取最新（`--latest true`）
- 若 `--latest false`，输出最多 10 条候选供手动选择
- 命中后会给出下一步命令（restore guide / manifest 查看）

## Trace Index / Trace Open
用于按 `trace_id` 聚合和打开全链路执行线索（history + deliveries + snapshots + 关键报告）。

生成 trace 索引：
```bash
./prompt-dsl-system/tools/run.sh trace-index -r .
```

按 trace 打开链路：
```bash
./prompt-dsl-system/tools/run.sh trace-open -r . --trace-id trace-c4d7
```

说明：
- `trace-index` 生成：
  - `prompt-dsl-system/tools/trace_index.json`
  - `prompt-dsl-system/tools/trace_index.md`
- `trace-open` 支持 trace_id 前缀匹配：
  - 默认 `--latest true` 返回最新一条
  - `--latest false` 输出候选列表（最多 10 条）
- 关联策略对工具根目录报告文件采用保守绑定：`mtime` 与 trace `last_seen_at` 在 `±24h` 窗口内才关联。

## Trace Diff（复盘对比）
用于对比两次 trace（A/B）在执行行为与风险信号上的差异，输出结构化报告和一页可读摘要。

示例 1（PASS -> FAIL 演进对比）：
```bash
./prompt-dsl-system/tools/run.sh trace-diff -r . --a trace-pass-abc --b trace-fail-def
```

示例 2（不同 pipeline 执行结果对比）：
```bash
./prompt-dsl-system/tools/run.sh trace-diff -r . --a trace-sql-001 --b trace-ownercommittee-002
```

示例 3（启用 deliveries 文件集合对比）：
```bash
./prompt-dsl-system/tools/run.sh trace-diff -r . --a trace-c4d7 --b trace-xxxx --scan-deliveries true --deliveries-depth 2 --limit-files 400
```

输出：
- `prompt-dsl-system/tools/trace_diff.json`
- `prompt-dsl-system/tools/trace_diff.md`

说明：
- trace_id 支持前缀匹配；默认 `--latest true` 自动取最新匹配项。
- 若 `--latest false` 且前缀命中多条，命令会返回候选列表并退出（exit 2），要求给更精确前缀。
- `scan-deliveries` 默认关闭，避免大目录扫描开销；开启后仅做路径集合差异，不读取文件内容。

## Trace Bisect（PASS->FAIL 最短排障）
用于在一次坏 trace（FAIL）与一次好 trace（PASS）之间，自动生成 5~12 步最短排障路径。

示例 1（仅给 bad，自动找最近 PASS 作为 good）：
```bash
./prompt-dsl-system/tools/run.sh trace-bisect -r . --bad trace-FAIL
```

示例 2（显式指定 good/bad）：
```bash
./prompt-dsl-system/tools/run.sh trace-bisect -r . --bad trace-FAIL --good trace-PASS
```

输出：
- `prompt-dsl-system/tools/bisect_plan.json`
- `prompt-dsl-system/tools/bisect_plan.md`
- `prompt-dsl-system/tools/bisect_plan.sh`（默认 `DRY_RUN=1`）

说明：
- 若自动找不到 good，会在计划中标记 `good_missing=true`，并提示手动指定 `--good`。
- 计划优先级按：P0 bypass -> P1 verify -> P2 guard -> P3 loop -> P4 snapshot/deliveries。
- `bisect_plan.sh` 默认只回显命令，不执行破坏性动作；需要显式设置 `DRY_RUN=0` 才执行。

## verify-followup-fixes（残留引用验收）
用于迁移/补丁后的只读验收步骤：扫描 repo 内是否仍残留旧引用 token，并输出 PASS/WARN/FAIL 报告。

输入：
- 必填 `--moves`：支持 `conflict_plan.json` / `moves_mapping_*.json` / `move_report.json`
- 可选 `--scan-report`：复用 scanner 产生的 tokens
- 可选 `--patch-plan`：加入 patch plan 的 `from` 字符串进行残留检查

输出：
- `followup_verify_report.json`
- `followup_verify_report.md`

状态规则：
- `PASS`: `hits_total == 0`
- `WARN`: `0 < hits_total <= 20`
- `FAIL`: `hits_total > 20`，或命中发生在 `src/main/java` / `pages` 且 token 属于 `exact_paths` / `fqcn_hints`

示例：
```bash
./prompt-dsl-system/tools/run.sh verify-followup-fixes -r . \
  --moves prompt-dsl-system/tools/moves_mapping_rename_suffix.json

./prompt-dsl-system/tools/run.sh verify-followup-fixes -r . \
  --moves prompt-dsl-system/tools/moves_mapping_rename_suffix.json \
  --scan-report prompt-dsl-system/tools/followup_scan_report_rename_suffix.json \
  --patch-plan prompt-dsl-system/tools/followup_patch_plan.json
```

## 自监控（anti-loop）
`run` 命令在生成 `run_plan.yaml` 后会自动执行 loop 检测：
- 默认行为：只警告，不阻断；同时自动触发 advisory debug-guard 并刷新 `guard_report + move/rollback plans`。
- 检测信号：文件集绕圈、越界反复、影响域扩张、无 module_path 盲跑。
- 新增最高优先级检测：`release_gate_bypass_attempt`。
  - 当 recent window 内多次出现 `verify_status=FAIL` 且仍尝试推进型命令（`run/apply-move/apply-followup-fixes`）时触发 `LOOP_HIGH`。
  - 命中后会建议先把 `verify-followup-fixes` 跑到 `PASS`，并保持 `--verify-gate true`。

强制阻断（仅 HIGH 级别）：

```bash
./prompt-dsl-system/tools/run.sh run -r . -m <MODULE_PATH> --pipeline <PIPELINE> --fail-on-loop
```

常用参数：
- `--loop-window <N>`：窗口大小（默认 6）
- `--loop-output-dir <PATH>`：诊断与计划输出目录（默认 `prompt-dsl-system/tools`）
- `--loop-same-trace-only true|false`：默认 `true`（仅看同 `trace_id`）

输出物：
- `trace_history.jsonl`
- `loop_diagnostics.json` / `loop_diagnostics.md`
- `guard_report.json` + `move_plan.*` + `rollback_plan.*`

推荐开启：
- `--fail-on-loop`
- `--verify-gate true`（默认值）

## Risk Gate（高风险必须 ACK）
当 guard 或 loop 判定风险达到阈值（默认 `HIGH`）时，`run` 会被硬阻断，必须提供一次性 `ACK token` 才允许继续。

基础流程：

```bash
./prompt-dsl-system/tools/run.sh run -r . -m <MODULE_PATH> --pipeline <PIPELINE>
# 若被阻断，查看 prompt-dsl-system/tools/RISK_GATE_TOKEN.txt
./prompt-dsl-system/tools/run.sh run -r . -m <MODULE_PATH> --pipeline <PIPELINE> --ack <TOKEN>
```

说明：
- token 绑定上下文：`repo_root + overall_risk + reason_hash + expires_at`，不可跨上下文复用。
- token 默认有效期 30 分钟，可通过 `--risk-ttl-minutes` 调整。
- 同一 token 为一次性，成功放行后会被标记 consumed。
- 风险上下文变化（例如 loop 触发器变化）会导致旧 token 失效并重新签发。

常用参数：
- `--risk-gate true|false`（默认 `true`）
- `--no-risk-gate`（显式关闭）
- `--risk-threshold LOW|MEDIUM|HIGH`（默认 `HIGH`）
- `--risk-ttl-minutes <N>`（默认 `30`）
- `--risk-exit-code <CODE>`（默认 `4`）

重新签发 token：
- 直接重跑同一条 `run` 命令（不带或带无效 `--ack`）即可自动生成新 token。

## 半自动放行提示
默认情况下，当 `run` 被 risk gate 阻断（exit `4`）时，`run.sh` 会检查最近生成的 token，并给出“最短放行命令”提示：

```bash
./prompt-dsl-system/tools/run.sh run -r . -m <MODULE> --pipeline <PIPELINE>
# 阻断后会提示：追加 --ack-latest
```

也支持显式指定 token 文件：

```bash
./prompt-dsl-system/tools/run.sh run -r . -m <MODULE> --pipeline <PIPELINE> --ack-file prompt-dsl-system/tools/RISK_GATE_TOKEN.json
```

可选参数：
- `--ack-hint-window <seconds>`：token 新鲜窗口，默认 `10` 秒。
- `--no-ack-hint`：关闭阻断后的放行提示（适合 CI 静默场景）。

## 自动重试（可选）
默认安全策略是“只提示，不自动重试”。如果你要一键重试一次，可显式开启：

```bash
./prompt-dsl-system/tools/run.sh run -r . -m <MODULE> --pipeline <PIPELINE> --auto-ack-latest
```

行为说明：
- 仅在 risk gate 阻断（exit `4`）后触发。
- 只重试一次，避免循环重试。
- 仍然依赖最新 token 有效；若 token 过期/上下文变更，会继续阻断并保持 exit `4`。
- `run.sh` 会读取 `risk_gate_report.json` 的策略字段（`auto_ack_allowed` / `auto_ack_denied_reason` / `move_plan_*`）再决定是否自动重试。

自动重试策略（升级版，默认保守）：
- `forbidden`：永不自动放行，必须手动 ACK。
- `outside_module`：仅当 move plan 已生成、全部可迁移、且 `high_risk=0`（无 `dst exists` 冲突）才允许自动重试。
- `loop HIGH`（无 forbidden/outside/missing-module）：允许自动重试一次。
- `missing module_path`：不自动，必须先补 `-m/--module-path`。
- `release_gate_bypass_attempt`：强制禁用 auto-ack，必须人工 ACK。

## Release Gate（验收闸门）
`followup_verify_report.json` 现在是推进型命令的验收门禁输入。默认策略：
- `verify=FAIL`：必须经过 risk gate 并提供 ACK（exit `4` 阻断）。
- `verify=WARN`：默认不 gate（可配置为 `--verify-threshold WARN`）。
- `verify=PASS`：不触发 verify gate。

受影响的推进型命令：
- `run`
- `apply-move`（真实执行：`--yes --move-dry-run false`）
- `apply-followup-fixes`（真实执行：`--mode apply --yes --dry-run false`）

常用参数（透传到 `pipeline_runner.py`）：
- `--verify-gate true|false`（默认 `true`）
- `--verify-threshold PASS|WARN|FAIL`（默认 `FAIL`）
- `--verify-report <path>`（默认 `prompt-dsl-system/tools/followup_verify_report.json`）
- `--verify-refresh true|false`（默认 `false`；开启后会在 gate 前尝试刷新 verify 报告）

推荐工作流：
1. `verify-followup-fixes` 先跑到 `PASS`。
2. 再执行 `run` / `apply-move` / `apply-followup-fixes`。
3. 若被 gate 阻断，读取 token 后用 `--ack-latest` 放行（人工确认）。

带人工理由记录（建议在 verify FAIL + ACK 推进时使用）：

```bash
./prompt-dsl-system/tools/run.sh run -r . -m <MODULE_PATH> --pipeline <PIPELINE> \
  --ack-latest \
  --ack-note "紧急发布窗口，已人工确认残留命中为文档引用，不影响运行"
```

说明：
- `--ack-note` 为可选，不阻断自动化流程。
- 若提供，会写入 `prompt-dsl-system/tools/ack_notes.jsonl` 便于审计追踪。

示例：

```bash
# verify FAIL 时会拦截，需要 ACK
./prompt-dsl-system/tools/run.sh run -r . -m <MODULE_PATH> --pipeline <PIPELINE>
./prompt-dsl-system/tools/run.sh run -r . -m <MODULE_PATH> --pipeline <PIPELINE> --ack-latest

# 临时关闭 verify gate（不建议，故障排查场景）
./prompt-dsl-system/tools/run.sh run -r . -m <MODULE_PATH> --pipeline <PIPELINE> --verify-gate false

# 将 WARN 也作为 gate 阈值
./prompt-dsl-system/tools/run.sh apply-followup-fixes -r . --scan-report <SCAN_REPORT> \
  --mode apply --yes --dry-run false --verify-threshold WARN
```
