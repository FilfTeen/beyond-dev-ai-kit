# HEALTH_REPORT_TEST_NOTES

## Scope
- Repo: `beyond-dev-ai-kit`
- Date: 2026-02-10 (UTC)
- Interpreter: `/usr/bin/python3`

## Case 1: trace_history 不存在

### Command
```bash
/usr/bin/python3 prompt-dsl-system/tools/health_reporter.py \
  --repo-root . \
  --validate-report prompt-dsl-system/tools/validate_report.json \
  --trace-history prompt-dsl-system/tools/_missing_trace_history.jsonl \
  --window 5 \
  --output-dir prompt-dsl-system/tools
```

### Expected
- 仍生成 `health_report.json` / `health_report.md`。
- `Execution Signals` 为空（`window_records=0`）。
- 报告里标注 trace 缺失 warning。

### Actual
- 生成成功。
- `window_records=0`。
- `sources.trace_load_warnings` 包含 missing trace 提示。

---

## Case 2: window=5 生效

### Command
```bash
./prompt-dsl-system/tools/run.sh validate -r . --health-window 5
```

### Expected
- 健康报告生成。
- `health_report.json.window=5`。
- 仅统计最近 5 条 trace。

### Actual
- 生成成功。
- `window=5`，`execution_signals.total_runs=5`。

---

## Case 3: validate 后自动生成 health_report

### Command
```bash
./prompt-dsl-system/tools/run.sh validate -r .
```

### Expected
- stdout 包含健康报告路径。
- 生成文件：
  - `prompt-dsl-system/tools/health_report.md`
  - `prompt-dsl-system/tools/health_report.json`

### Actual
- stdout 包含：
  - `Health report generated: prompt-dsl-system/tools/health_report.md`
  - `[hongzhi] health_report=prompt-dsl-system/tools/health_report.md`
- 文件已生成。

