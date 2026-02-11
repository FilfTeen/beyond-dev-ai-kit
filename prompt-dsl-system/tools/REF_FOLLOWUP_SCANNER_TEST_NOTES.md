# REF_FOLLOWUP_SCANNER Test Notes

Generated at: 2026-02-10 (local)

## Scope
- `ref_followup_scanner.py` 静态扫描逻辑（`rg` 优先，`grep` 回退）
- `move_conflict_resolver.py` 生成三策略 follow-up 清单
- `pipeline_runner.py` / `run.sh` 的 `scan-followup` 入口

## Case 1: `rg` 存在路径
- Command:
```bash
/usr/bin/python3 prompt-dsl-system/tools/ref_followup_scanner.py \
  --repo-root . \
  --moves prompt-dsl-system/tools/_tmp_ref_followup/moves.json \
  --output-dir prompt-dsl-system/tools/_tmp_ref_followup/out_rg \
  --max-hits-per-move 3 \
  --use-rg true
```
- Result:
  - 成功生成：
    - `followup_scan_report.json`
    - `followup_checklist.md`
  - `followup_scan_report.json` 中 `scanner="rg"`。

## Case 2: `grep` 回退路径（模拟 `rg` 不可用）
- 验证方式：显式传 `--use-rg false` 强制走 `grep` 分支。
- Command:
```bash
/usr/bin/python3 prompt-dsl-system/tools/ref_followup_scanner.py \
  --repo-root . \
  --moves prompt-dsl-system/tools/_tmp_ref_followup/moves.json \
  --output-dir prompt-dsl-system/tools/_tmp_ref_followup/out_grep \
  --max-hits-per-move 5 \
  --use-rg false
```
- Result:
  - 成功生成同名产物。
  - `followup_scan_report.json` 中 `scanner="grep"`。

## Case 3: move mapping 扫描命中
- Fixture: `moves.json` 包含 `src -> dst`，并在 `app.xml` 中写入旧路径/FQCN/文件名引用。
- Result:
  - `hits[]` 正常记录 `file/line/snippet/matched_token`。
  - `recommendations[]` 生成 `manual_review` + `candidate_replace`（含 path 与 java FQCN 候选）。

## Case 4: max-hits 截断
- 输入中重复多次相同 token，设置较小阈值 `--max-hits-per-move 3`。
- Result:
  - `moves[0].truncated=true`
  - `hits` 数量受限于阈值，超出部分保留在后续人工复扫流程中处理。

## Case 5: resolve-move-conflicts 自动附带三策略 checklist
- Command:
```bash
/usr/bin/python3 prompt-dsl-system/tools/move_conflict_resolver.py \
  --repo-root . \
  --module-path prompt-dsl-system/tools/_tmp_conflict_followup/module \
  --move-report prompt-dsl-system/tools/_tmp_conflict_followup/out/move_report.json \
  --output-dir prompt-dsl-system/tools/_tmp_conflict_followup/out \
  --mode plan --strategy rename_suffix
```
- Result:
  - 生成三策略 mapping + 清单 + 报告：
    - `moves_mapping_rename_suffix.json` / `moves_mapping_imports_bucket.json` / `moves_mapping_abort.json`
    - `followup_checklist_rename_suffix.md` / `followup_checklist_imports_bucket.md` / `followup_checklist_abort.md`
    - `followup_scan_report_rename_suffix.json` / `followup_scan_report_imports_bucket.json` / `followup_scan_report_abort.json`
  - `conflict_plan.md` 已引用上述 checklist/report 路径。

## Case 6: apply 后二次扫描
- Command sequence:
  - 先不带 ACK 执行 apply，触发 risk gate（exit 4，签发 token）
  - 再带 `--ack-latest` 执行 apply
- Result:
  - apply 成功后额外生成：
    - `followup_checklist_after_apply.md`
    - `followup_scan_report_after_apply.json`
  - 控制台输出下一步提示：按 checklist 修引用，再执行 `debug-guard` 与 `validate`。

