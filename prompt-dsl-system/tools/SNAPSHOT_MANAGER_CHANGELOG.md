# SNAPSHOT_MANAGER Changelog

## 新增/修改文件
- `prompt-dsl-system/tools/snapshot_manager.py` (new)
- `prompt-dsl-system/tools/pipeline_runner.py` (updated)
- `prompt-dsl-system/tools/run.sh` (updated)
- `prompt-dsl-system/tools/README.md` (updated)
- `prompt-dsl-system/tools/SNAPSHOT_MANAGER_TEST_NOTES.md` (new)

## 功能摘要
- 新增 `snapshot_manager.py`：在 apply 前创建快照目录，输出：
  - `manifest.json` / `manifest.md`
  - `vcs_detect.json`
  - `status.txt`
  - `changed_files.txt`
  - `diff.patch`
  - `inputs/`（关键输入报告拷贝）
  - `notes.md`
- `pipeline_runner.py` 在真实写盘前自动触发快照：
  - `apply-move` (`--yes --move-dry-run false`)
  - `resolve-move-conflicts --mode apply --yes --dry-run false`
  - `apply-followup-fixes --mode apply --yes --dry-run false`
- 快照失败默认阻断（exit 2）；可通过 `--no-snapshot` 显式绕过。
- trace 记录新增 snapshot 字段：
  - `snapshot_created`
  - `snapshot_path`
  - `snapshot_label`

## 默认阻断策略
- apply 类命令在“真正写盘前”必须先拿到 snapshot。
- snapshot 失败立即 fail-fast（exit 2），避免无恢复点直接改盘。
- `--no-snapshot` 为显式风险开关，默认关闭（不建议）。

## 快照目录结构
- 根目录：`prompt-dsl-system/tools/snapshots/`
- 单次快照：`snapshot_<timestamp>_<trace_or_context>/`
- 关键文件：
  - `manifest.json`, `manifest.md`, `status.txt`, `changed_files.txt`, `diff.patch`, `inputs/`, `notes.md`

## 回滚提示
- Git（全量，谨慎）：`git reset --hard && git clean -fd`
- SVN（全量，谨慎）：`svn revert -R .`
- 部分文件回退：`git restore -- <path>` 或 `svn revert <path>`

## 风险说明
- `--no-snapshot` 会降低可恢复性，仅建议在明确知道后果时使用。
- 无 VCS 场景下 `diff.patch` 可能为 `UNAVAILABLE`，但仍会保留状态与输入报告快照。
