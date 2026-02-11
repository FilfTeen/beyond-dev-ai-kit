# A2_conversion_report

- context_id: ctx-3a70562661bc
- trace_id: trace-c4d7acea934f4bbbb5a8979a1de7051b
- input_artifact_refs: ["A1"]

## Per-file Conversion Notes
- 01_drop_tables.sql
  - Replaced Oracle PL/SQL exception DROP blocks with DM8 DROP TABLE IF EXISTS ... CASCADE.
- 02_create_public_notice.sql
  - Replaced VARCHAR2 -> VARCHAR occurrences: 23.
- 03_create_public_notice_scope.sql
  - Replaced VARCHAR2 -> VARCHAR occurrences: 2.
- 04_create_public_notice_cover.sql
  - Replaced VARCHAR2 -> VARCHAR occurrences: 3.
- 05_create_public_notice_external_source.sql
  - Replaced VARCHAR2 -> VARCHAR occurrences: 10.
  - Removed Oracle-only identifier-limit fallback block and duplicate CREATE TABLE section.
- 06_create_index.sql
  - No syntax change required for DM8 execution baseline.
- 07_create_public_notice_read.sql
  - Replaced VARCHAR2 -> VARCHAR occurrences: 5.
- 08_upgrade_from_legacy.sql
  - Replaced VARCHAR2 -> VARCHAR occurrences: 23.
- 10_menu_and_role_config.sql
  - No syntax change required for DM8 execution baseline.
