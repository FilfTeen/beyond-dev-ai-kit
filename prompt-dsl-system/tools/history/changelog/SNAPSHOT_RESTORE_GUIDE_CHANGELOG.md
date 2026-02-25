# SNAPSHOT_RESTORE_GUIDE Changelog

## 新增/修改文件清单
- `prompt-dsl-system/tools/snapshot_restore_guide.py` (new)
- `prompt-dsl-system/tools/pipeline_runner.py` (updated)
- `prompt-dsl-system/tools/run.sh` (updated)
- `prompt-dsl-system/tools/README.md` (updated)
- `prompt-dsl-system/tools/SNAPSHOT_RESTORE_GUIDE_TEST_NOTES.md` (new)

## 脚本策略
- 新增 `snapshot_restore_guide.py`：读取 snapshot 目录（`manifest.json`/`diff.patch`/`changed_files.txt`）生成：
  - `restore_guide.md`
  - `restore_full.sh`
  - `restore_files.sh`
  - `restore_check.json`
- `pipeline_runner.py` 新增子命令：
  - `snapshot-restore-guide`
- `run.sh` 新增转发入口：
  - `./prompt-dsl-system/tools/run.sh snapshot-restore-guide ...`

## DRY_RUN 机制
- 生成的 `restore_full.sh` / `restore_files.sh` 默认 `DRY_RUN=1`。
- 只有显式 `DRY_RUN=0 <script>` 才会执行破坏性回滚命令。

## 回滚安全注意事项
- 优先按文件回滚（`restore_files.sh`），再考虑全量回滚（`restore_full.sh`）。
- strict 模式默认开启：snapshot 与当前 repo_root 不一致时会阻断（exit 2）。
- 真实执行前请确认当前改动可丢弃，避免误清理未提交内容。
