# A2_portability_patch_notes

- context_id: ctx-3a70562661bc
- trace_id: trace-c4d7acea934f4bbbb5a8979a1de7051b

## Rewrite Strategy Rules
1. Replace `VARCHAR2(n)` -> `VARCHAR(n)`.
2. Replace Oracle PL/SQL DROP blocks + `PURGE` with DM8 `DROP TABLE IF EXISTS <table> CASCADE;`.
3. Keep statement order and comments where possible.
4. Keep table/column names unchanged.
5. Remove Oracle-only fallback section in `05_create_public_notice_external_source.sql` that duplicates DDL.

## Scope
- 01_drop_tables.sql
- 02_create_public_notice.sql
- 03_create_public_notice_scope.sql
- 04_create_public_notice_cover.sql
- 05_create_public_notice_external_source.sql
- 06_create_index.sql
- 07_create_public_notice_read.sql
- 08_upgrade_from_legacy.sql
- 10_menu_and_role_config.sql
