# TRACE_INDEX_OPEN Test Notes

## Case 1: 生成 trace_index
- Command:
```bash
./prompt-dsl-system/tools/run.sh trace-index -r .
```
- Expected:
  - 生成 `trace_index.json` 与 `trace_index.md`
  - items 按 last_seen_at 降序
- Actual:
  - 命令可执行并产出索引文件。

## Case 2: trace-open 命中 deliveries 与 snapshot
- Command:
```bash
./prompt-dsl-system/tools/run.sh trace-open -r . --trace-id trace-index-open-001
```
- Expected:
  - 输出 trace 基本信息
  - 输出路径清单（至少包含 snapshot_paths，若存在则包含 deliveries_dir）
  - 输出下一步命令（health/risk/verify/restore/index）
- Actual:
  - 命中后返回全链路路径与下一步命令建议。

## Case 3: 前缀匹配多条 + latest=false
- Command:
```bash
./prompt-dsl-system/tools/run.sh trace-open -r . --trace-id trace- --latest false
```
- Expected:
  - 输出 top 10 候选列表
  - exit 0
- Actual:
  - 多匹配场景下按 last_seen_at 倒序输出候选。
