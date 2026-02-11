# TRACE_INDEX_OPEN Changelog

## 新增/修改文件清单
- `prompt-dsl-system/tools/trace_indexer.py` (new)
- `prompt-dsl-system/tools/trace_open.py` (new)
- `prompt-dsl-system/tools/pipeline_runner.py` (updated)
- `prompt-dsl-system/tools/run.sh` (updated)
- `prompt-dsl-system/tools/README.md` (updated)
- `prompt-dsl-system/tools/TRACE_INDEX_OPEN_TEST_NOTES.md` (new)

## 关联策略
- `trace_indexer` 聚合来源：
  - `trace_history.jsonl`（默认最近 `window=200` 条，`scan-all=true` 可全量）
  - `tools/deliveries/*`（目录名前缀匹配 trace_id）
  - `tools/snapshots/snapshot_*/manifest.json`（trace_id 匹配）
  - `tools/` 根目录关键报告（保守绑定）
- 报告文件保守绑定规则：
  - 仅当报告文件 mtime 与 trace `last_seen_at` 在 `±24h` 窗口内才关联
  - 采用最近时间匹配，避免误绑定旧报告

## 过滤与 latest 行为
- `trace-open --trace-id` 支持前缀匹配。
- 多匹配时：
  - 默认 `--latest true` 取最新
  - `--latest false` 输出 top 10 候选列表

## 回滚方式
- 无（本次为工具层索引/检索增强）。
