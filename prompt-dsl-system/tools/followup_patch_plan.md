# followup_patch_plan

- generated_at: 2026-02-10T03:47:49+00:00
- mode: plan
- scan_report: prompt-dsl-system/tools/followup_scan_report.json
- confidence_threshold: high
- max_changes: 100
- total_candidates: 0
- selected_candidates: 0
- total_replacements: 0
- files_changed: 0
- truncated: false

## Rules
- A_full_path: 完整旧路径字符串替换（高置信度）。
- B_frontend_old_dir/B_frontend_tail_dir: 前端静态资源路径上下文替换（高置信度）。
- C_java_fqcn: Java/XML import/class/mapper 等上下文 FQCN 替换（高置信度）。
- 禁止：basename-only、SQL 语义级、二进制文件。

## File Changes
- no patchable high-confidence replacements

