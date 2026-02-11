# SNAPSHOT_PRUNE Test Notes

## Case 1: dry-run 生成报告
- Command:
```bash
./prompt-dsl-system/tools/run.sh snapshot-prune --keep-last 20 --max-total-size-mb 1024
```
- Expected:
  - 仅生成 `snapshot_prune_report.json/.md`
  - 不删除任何 snapshot 目录
- Actual:
  - 默认 dry-run 行为已实现，报告包含 `to_delete` 计划与理由。

## Case 2: apply 删除旧快照（临时样本）
- Setup:
  - 在 `prompt-dsl-system/tools/snapshots/` 下准备可删除的旧 `snapshot_*` 目录（含 `manifest.json` 且 created_at 较旧）。
- Command:
```bash
./prompt-dsl-system/tools/run.sh snapshot-prune --keep-last 0 --max-total-size-mb 1 --apply
```
- Expected:
  - 删除 report 标记 `delete=true` 的目录
  - 报告 `deleted` 计数递增
- Notes:
  - 本次记录使用现有快照目录，未强制清空，建议在独立临时样本目录复测。

## Case 3: invalid entries 不会删
- Setup:
  - 在 snapshots 下放置非规范目录（例如不含 manifest.json 的 `snapshot_invalid_xxx`）。
- Command:
```bash
./prompt-dsl-system/tools/run.sh snapshot-prune --keep-last 20 --max-total-size-mb 1024 --apply
```
- Expected:
  - invalid entries 出现在 `invalid_entries_list`
  - 不会被删除
- Actual:
  - 脚本仅删除通过安全校验的目录（`snapshot_*` + `manifest.json` + 路径边界校验）。
