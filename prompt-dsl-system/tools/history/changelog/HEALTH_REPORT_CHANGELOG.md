# HEALTH_REPORT_CHANGELOG

## 变更目标
在 `validate` 末尾自动生成编排系统健康报告（registry/pipelines/trace/risk/verify 聚合），提升全局可观测性与系统性问题定位效率。

## 新增/修改文件清单
- 新增：`prompt-dsl-system/tools/health_reporter.py`
- 修改：`prompt-dsl-system/tools/pipeline_runner.py`
- 修改：`prompt-dsl-system/tools/run.sh`
- 修改：`prompt-dsl-system/tools/README.md`
- 新增：`prompt-dsl-system/tools/HEALTH_REPORT_TEST_NOTES.md`
- 新增：`prompt-dsl-system/tools/HEALTH_REPORT_CHANGELOG.md`

## 字段口径（核心）
1. Build Integrity（来自 `validate_report.json` + `skills.json`）
- `registry_entries`
- `pipelines_checked`
- `errors` / `warnings`
- `validate_status`（PASS/WARN/FAIL）
- `yaml_json_parity`（若存在）
- `skills_versions` / `skills_versions_top3`

2. Execution Signals（最近窗口 trace）
- `total_runs`（窗口内记录数）
- `command_distribution`
- `exit_code_distribution`
- `blocked_by_distribution`
- `verify_status_distribution`
- `ack_used_distribution`
- `overall_risk_distribution`（若 trace 中存在）
- `risk_proxy`（verify_fail/exit4/guard_gate 等）

3. Risk Triggers
- `loop_level`
- `top_triggers`（最多 10）
- `bypass_attempt_count`

4. Recommendations
- 3~7 条可执行建议，逐条对应统计证据。

## 默认窗口
- `--health-window` 默认 `20`。

## validate 新增参数
- `--health-window <int>`（默认 20）
- `--trace-history <path>`（默认 `prompt-dsl-system/tools/trace_history.jsonl`）
- `--no-health-report`（跳过自动生成）

## 回滚方式
- 恢复以下文件到升级前版本：
  - `prompt-dsl-system/tools/pipeline_runner.py`
  - `prompt-dsl-system/tools/run.sh`
  - `prompt-dsl-system/tools/README.md`
- 删除新增文件：
  - `prompt-dsl-system/tools/health_reporter.py`
  - `prompt-dsl-system/tools/HEALTH_REPORT_TEST_NOTES.md`
  - `prompt-dsl-system/tools/HEALTH_REPORT_CHANGELOG.md`
- 重新执行：
  - `./prompt-dsl-system/tools/run.sh validate -r .`

