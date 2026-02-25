# SNAPSHOT_INDEX_OPEN Changelog

## 新增/修改文件清单
- `prompt-dsl-system/tools/snapshot_indexer.py` (new)
- `prompt-dsl-system/tools/snapshot_open.py` (new)
- `prompt-dsl-system/tools/pipeline_runner.py` (updated)
- `prompt-dsl-system/tools/run.sh` (updated)
- `prompt-dsl-system/tools/README.md` (updated)
- `prompt-dsl-system/tools/SNAPSHOT_INDEX_OPEN_TEST_NOTES.md` (new)

## 过滤规则
- `snapshot-open` 支持：`--trace-id --snapshot-id --context-id --label`
- 多条件同时提供时为 AND 过滤。
- 无匹配时 exit 2，并提示先执行 `snapshot-index`。

## 默认 latest 行为
- `--latest` 默认 true：多匹配时自动取最新一条。
- `--latest false`：输出最多 10 条候选列表，不做自动选择。

## 额外行为
- `snapshot-open` 在 index 不存在时会自动触发 index 生成。
- `snapshot_manager` 创建 snapshot 后尝试自动刷新 index（失败不阻断 apply 流程）。

## 回滚方式
- 无（本次为工具新增与文档更新）。
