# REF_FOLLOWUP_SCANNER Changelog

Generated at: 2026-02-10 (local)

## 新增/修改文件清单
- Added `prompt-dsl-system/tools/ref_followup_scanner.py`
- Modified `prompt-dsl-system/tools/move_conflict_resolver.py`
- Modified `prompt-dsl-system/tools/pipeline_runner.py`
- Modified `prompt-dsl-system/tools/run.sh`
- Modified `prompt-dsl-system/tools/README.md`
- Added `prompt-dsl-system/tools/REF_FOLLOWUP_SCANNER_TEST_NOTES.md`

## 扫描策略摘要
- 输入兼容：
  - `conflict_plan.json`（支持按策略读取 `mappings`）
  - `move_report.json`（读取 `items[]` / `mappings[]`）
  - 纯 mapping JSON（`mappings[]`）
- token 构造（纯静态，不做业务推断）：
  - `basename`
  - `old_rel_path`
  - `old_rel_dir`
  - java 场景下 `old_fqcn_hint`（仅路径可推导时）
- 扫描优先级：
  - 优先 `rg`（`--use-rg true` 且系统可用）
  - 回退 `grep -R`
- 默认扫描文件类型：
  - `*.java, *.xml, *.yml, *.yaml, *.properties, *.json, *.js, *.ts, *.vue, *.html, *.xhtml, *.jsp, *.sql, *.md`
- 默认排除目录：
  - `.git, target, .idea, .vscode, node_modules, dist, build, out, logs`

## 输出说明
- 独立扫描输出：
  - `followup_scan_report.json`
  - `followup_checklist.md`
- 冲突策略输出（由 resolver 自动生成）：
  - `moves_mapping_<strategy>.json`
  - `followup_scan_report_<strategy>.json`
  - `followup_checklist_<strategy>.md`
- apply 成功后追加输出：
  - `followup_scan_report_after_apply.json`
  - `followup_checklist_after_apply.md`

## 性能注意事项
- 扫描按 token 执行，命中量大时建议缩小 `moves` 输入范围。
- 可通过 `--max-hits-per-move` 控制单 move 命中上限（默认 50，超出会截断并标记 `truncated=true`）。
- checklist 仅展示前 10 条命中，完整内容在 `followup_scan_report.json`。

