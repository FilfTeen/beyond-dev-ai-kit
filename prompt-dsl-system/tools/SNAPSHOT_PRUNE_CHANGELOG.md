# SNAPSHOT_PRUNE Changelog

## 新增/修改文件清单
- `prompt-dsl-system/tools/snapshot_prune.py` (new)
- `prompt-dsl-system/tools/pipeline_runner.py` (updated)
- `prompt-dsl-system/tools/run.sh` (updated)
- `prompt-dsl-system/tools/README.md` (updated)
- `prompt-dsl-system/tools/SNAPSHOT_PRUNE_TEST_NOTES.md` (new)

## 策略规则
- 仅扫描 `snapshots-dir` 下一级目录。
- 仅识别合法 snapshot：目录名 `snapshot_*` 且包含 `manifest.json`。
- 清理策略：
  - 保留最近 N 个（按 `created_at`）
  - 控制总大小上限（MB）
  - 标签过滤（`only-label` / `exclude-label`）
- 删除理由可审计（如 `older_than_keep_last`, `size_limit_exceeded`, `label_included`）。

## dry-run 安全
- 默认 `dry-run=true`，只生成报告不删除。
- 只有显式 `--apply` 才执行删除。
- 删除前再次做安全校验（路径边界 + manifest 存在）。

## 回滚说明
- 无自动回滚（删除不可逆）。
- 建议先 dry-run 审核 `snapshot_prune_report.json/.md` 再 apply。
