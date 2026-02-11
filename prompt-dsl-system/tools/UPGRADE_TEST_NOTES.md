# UPGRADE_TEST_NOTES

## Test Environment
- repo: `beyond-dev-ai-kit`
- runner wrapper: `prompt-dsl-system/tools/run.sh`
- python: `/usr/bin/python3`

## Case 1: run 未传 -m（强制边界）
- command:
```bash
./prompt-dsl-system/tools/run.sh run -r . --pipeline prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md
```
- expected:
  - fail-fast
  - stderr: `module-path is required for run (company guardrail)`
  - exit code = 2
- actual:
  - matched expected
  - exit code = 2

## Case 2: run 传 -m，改动在 module 内（pass）
- command:
```bash
./prompt-dsl-system/tools/run.sh run -r . -m prompt-dsl-system --pipeline prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md
```
- expected:
  - guard pass
  - run_plan.yaml generated
  - exit code = 0
- actual:
  - `[guard] decision=pass`
  - run plan generated
  - exit code = 0

## Case 3: run 传 -m，改动在 module 外（fail-fast）
- command:
```bash
HONGZHI_GUARD_CHANGED_FILES="src/main/java/com/indihx/ownercommittee/service/Foo.java" \
./prompt-dsl-system/tools/run.sh run -r . -m prompt-dsl-system --pipeline prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md
```
- expected:
  - rule `out_of_allowed_scope`
  - fail-fast exit 2
  - stdout/stderr 包含 guard_report 路径
- actual:
  - primary rule: `out_of_allowed_scope (src/main/java/com/indihx/ownercommittee/service/Foo.java)`
  - `guard report: prompt-dsl-system/tools/guard_report.json`
  - exit code = 2

## Case 4: debug-guard（advisory 不阻断）
- command:
```bash
HONGZHI_GUARD_CHANGED_FILES="src/main/java/com/indihx/util/Leak.java" \
./prompt-dsl-system/tools/run.sh debug-guard -r . -m prompt-dsl-system
```
- expected:
  - advisory 模式下报告 fail 但进程不阻断
  - 输出 guard 规则摘要
  - 生成 `guard_report.json`
- actual:
  - `[guard] decision=fail` + `[guard][warn] advisory=true; violations reported without blocking`
  - 输出 forbidden/ignore/effective module/allow set
  - exit code = 0

## Baseline Verify
- command:
```bash
./prompt-dsl-system/tools/run.sh validate -r .
```
- result:
  - `Errors: 0`
  - `Warnings: 0`
