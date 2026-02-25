# HEALTH_RUNBOOK_CHANGELOG

## 变更目标
基于 `health_report.json` 自动生成“最短收敛路径” runbook（md + sh + json），用于收敛风险、恢复可推进状态。默认仅生成文件，不执行命令。

## 新增/修改文件清单
- 新增：`prompt-dsl-system/tools/health_runbook_generator.py`
- 修改：`prompt-dsl-system/tools/pipeline_runner.py`
- 修改：`prompt-dsl-system/tools/run.sh`
- 修改：`prompt-dsl-system/tools/README.md`
- 新增：`prompt-dsl-system/tools/HEALTH_RUNBOOK_TEST_NOTES.md`
- 新增：`prompt-dsl-system/tools/HEALTH_RUNBOOK_CHANGELOG.md`

## 决策树规则摘要
1. `validate.errors > 0`
- 优先重复 `validate`，禁止推进。

2. `bypass_attempt_count >= 1`
- 先跑 `verify-followup-fixes` 收敛 FAIL，再做 `run` plan。
- ack 仅提供说明，不自动加入命令。

3. `verify FAIL`（比例>0）
- `verify-followup-fixes` -> `apply-followup-fixes --mode plan` -> 再次 `verify`。

4. `blocked_by` 以 `guard_gate` 为主
- `debug-guard` -> `apply-move`(plan) -> `resolve-move-conflicts`(plan)。

5. `blocked_by` 以 `loop_gate` 为主
- `validate` -> `run --fail-on-loop` -> 人工收敛循环面。

## safe / aggressive 差异
- `safe`（默认）：
  - 只生成只读/plan 命令。
  - 不包含 `--mode apply`。
  - 不包含 `--ack` / `--ack-latest` 执行命令。
- `aggressive`：
  - 可额外给出 apply 模板命令，但默认仍为 `--dry-run true`（不执行实际修改）。

## validate 新参数
- `--no-health-runbook`：跳过 runbook 自动生成。
- `--runbook-mode safe|aggressive`：默认 `safe`。

## 回滚方式
1. 恢复文件：
- `prompt-dsl-system/tools/pipeline_runner.py`
- `prompt-dsl-system/tools/run.sh`
- `prompt-dsl-system/tools/README.md`
2. 删除新增：
- `prompt-dsl-system/tools/health_runbook_generator.py`
- `prompt-dsl-system/tools/HEALTH_RUNBOOK_TEST_NOTES.md`
- `prompt-dsl-system/tools/HEALTH_RUNBOOK_CHANGELOG.md`
3. 重新验收：
```bash
./prompt-dsl-system/tools/run.sh validate -r .
```

