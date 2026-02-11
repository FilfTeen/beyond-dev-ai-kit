# A1_release_migration_runbook

- context_id: ctx-3a70562661bc
- trace_id: trace-c4d7acea934f4bbbb5a8979a1de7051b
- module_path: /Users/dwight/Downloads/HongzhiTechnology_SvnRepository/Project/xiangyang/zhihuiwuye/4coding/xywygl/src/main/java/com/indihx/notice

## Batch Plan
### Batch 0 - Precheck
1. Confirm target schema is DM8 and backup policy is ready.
2. Review Step1/Step2/Step3 artifacts and approve risk acceptance.

### Batch 1 - Destructive DDL (Optional/Fresh Install)
- Execute converted `01_drop_tables.sql` segment only when refresh is intended.
- Rollback point: stop immediately if non-target objects are touched.

### Batch 2 - Core Schema
- Execute create scripts in order: 02 -> 03 -> 04 -> 05 -> 07.
- Execute index script 06 after table creation.

### Batch 3 - Upgrade and Config
- Execute 08 only for legacy schema upgrade scenarios.
- Execute 10 menu/role config in controlled permission window.

### Batch 4 - Verification and Handover
- Run checklist in A2_verification_checklist.md.
- Archive SQL execution logs with trace_id in filename.

## Rollback
1. If schema creation fails mid-way, rollback via pre-migration backup restore.
2. If only non-structural DML fails (menu/role), rollback DML transaction and re-run after correction.
3. Keep converted SQL immutable; patch by new delta script, not ad-hoc edits in production.
