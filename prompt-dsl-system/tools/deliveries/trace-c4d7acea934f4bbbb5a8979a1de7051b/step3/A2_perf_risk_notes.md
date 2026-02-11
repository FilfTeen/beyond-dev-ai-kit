# A2_perf_risk_notes

- context_id: ctx-3a70562661bc
- trace_id: trace-c4d7acea934f4bbbb5a8979a1de7051b

## Execution-order and lock considerations
1. Run DDL in small batches by file order to isolate failures.
2. If volume import is required, create core tables first, load data, then create secondary indexes.
3. Keep menu/role config DML (`10_menu_and_role_config.sql`) in a separate transaction window.
4. Avoid concurrent schema changes during migration window to reduce metadata lock contention.

## Potential lock points
- `ALTER TABLE ... ADD ...` in `08_upgrade_from_legacy.sql` can hold metadata locks.
- Multiple index creations on `PUBLIC_NOTICE` may increase lock time on large data sets.
- DML into `SYS_MENU_INFO` / `SYS_ROLE_MENU` requires controlled permission and change window.
