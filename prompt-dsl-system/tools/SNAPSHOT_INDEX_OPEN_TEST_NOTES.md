# SNAPSHOT_INDEX_OPEN Test Notes

## Case 1: index 生成
- Command:
```bash
./prompt-dsl-system/tools/run.sh snapshot-index
```
- Expected:
  - 生成 `snapshot_index.json` 和 `snapshot_index.md`
  - items 按 created_at 降序
- Actual:
  - index 命令可正常输出路径并生成文件。

## Case 2: open 按 trace-id 命中
- Command:
```bash
./prompt-dsl-system/tools/run.sh snapshot-open --trace-id <TRACE_ID>
```
- Expected:
  - 输出 best match：path/snapshot_id/trace_id/label/created_at
  - 输出下一步命令（snapshot-restore-guide + cat manifest）
- Actual:
  - 命中后返回文本结果并附建议命令。

## Case 3: 多条匹配 latest=false 列表输出
- Command:
```bash
./prompt-dsl-system/tools/run.sh snapshot-open --label <LABEL> --latest false
```
- Expected:
  - 输出最多 10 条候选并 exit 0
- Actual:
  - 多匹配时按 created_at 降序列出候选，便于人工选择。
