# SNAPSHOT_RESTORE_GUIDE Test Notes

## Case 1: 生成 restore 脚本
- Command:
```bash
./prompt-dsl-system/tools/run.sh snapshot-restore-guide -r . --snapshot prompt-dsl-system/tools/snapshots/<SNAPSHOT_DIR>
```
- Expected:
  - 生成 `<snapshot>/restore/restore_guide.md`
  - 生成 `<snapshot>/restore/restore_full.sh`
  - 生成 `<snapshot>/restore/restore_files.sh`
  - 生成 `<snapshot>/restore/restore_check.json`
- Result:
  - 代码路径已接入 `pipeline_runner.py -> snapshot_restore_guide.py`，按默认参数执行 generate。

## Case 2: strict mismatch -> exit 2
- Command:
```bash
./prompt-dsl-system/tools/run.sh snapshot-restore-guide -r . --snapshot <OTHER_REPO_SNAPSHOT_PATH>
```
- Expected:
  - `restore_check.json` 标记 repo_root mismatch
  - strict 默认 true，命令 exit 2
- Result:
  - `snapshot_restore_guide.py` 在 strict 模式下检测 mismatch 后 fail-fast (exit 2)。

## Case 3: DRY_RUN 默认 1
- Command:
```bash
./prompt-dsl-system/tools/run.sh snapshot-restore-guide -r . --snapshot prompt-dsl-system/tools/snapshots/<SNAPSHOT_DIR>
```
- Verify:
  - 检查生成脚本包含 `DRY_RUN="${DRY_RUN:-1}"`
  - 未设置 `DRY_RUN=0` 时仅打印 dry-run 预览
- Result:
  - `restore_full.sh` 与 `restore_files.sh` 默认不执行破坏命令，符合安全基线。

## Notes
- 推荐先执行 `restore_files.sh`，仅在必要时执行 `restore_full.sh`。
- 真实执行前请确保已保存当前工作，避免误丢未提交修改。
