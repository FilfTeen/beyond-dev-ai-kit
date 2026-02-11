# conflict_plan

- generated_at: 2026-02-10T03:38:30+00:00
- module_path_normalized: prompt-dsl-system/tools
- move_report: prompt-dsl-system/tools/move_report.json
- conflict_count: 0

## Status
- no conflicts

## Strategy Scripts
- rename_suffix: `prompt-dsl-system/tools/conflict_plan_strategy_rename_suffix.sh`
- imports_bucket: `prompt-dsl-system/tools/conflict_plan_strategy_imports_bucket.sh`
- abort: `prompt-dsl-system/tools/conflict_plan_strategy_abort.sh`

## 引用修复清单（静态扫描）
- 说明：以下清单仅为静态候选结果，不做业务推断，必须人工确认。
- rename_suffix checklist: `prompt-dsl-system/tools/followup_checklist_rename_suffix.md`
- rename_suffix report: `prompt-dsl-system/tools/followup_scan_report_rename_suffix.json`
- imports_bucket checklist: `prompt-dsl-system/tools/followup_checklist_imports_bucket.md`
- imports_bucket report: `prompt-dsl-system/tools/followup_scan_report_imports_bucket.json`
- abort checklist: `prompt-dsl-system/tools/followup_checklist_abort.md`
- abort report: `prompt-dsl-system/tools/followup_scan_report_abort.json`

## Execute (safe defaults)
- plan only:
  `./prompt-dsl-system/tools/run.sh resolve-move-conflicts -r . -m <MODULE_PATH> --strategy rename_suffix`
- apply (requires ACK + explicit yes):
  `./prompt-dsl-system/tools/run.sh resolve-move-conflicts -r . -m <MODULE_PATH> --strategy rename_suffix --mode apply --yes --dry-run false --ack-latest`
