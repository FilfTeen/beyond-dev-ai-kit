# A0_all_artifacts_full

- context_id: ctx-3a70562661bc
- trace_id: trace-c4d7acea934f4bbbb5a8979a1de7051b
- generated_at: 2026-02-09T10:01:00Z

## step1/A1_portability_risk_report.md

```md
# A1_portability_risk_report

- context_id: ctx-3a70562661bc
- trace_id: trace-c4d7acea934f4bbbb5a8979a1de7051b
- module_path: /Users/dwight/Downloads/HongzhiTechnology_SvnRepository/Project/xiangyang/zhihuiwuye/4coding/xywygl/src/main/java/com/indihx/notice
- scanned_sql_files: 9

## Objective Used
```yaml
inputs:
  - input_sql_path: "{{module_path}}/sql/*.sql"
  - include_patterns: ["*.sql"]
  - exclude_patterns: ["**/target/**", "**/node_modules/**"]
constraints:
  - only syntax migration (Oracle -> DM8)
  - do not change table structures or column semantics
  - keep comments and statement order as much as possible
  - output must be executable on DM8
acceptance:
  - A1: portability audit report (risk grading + exact locations)
  - A2: dm8 converted sql script (single merged file + per-file notes)
  - A3: index/constraint performance review report (if applicable)
  - A4: migration runbook (batches + verification + rollback)
forbidden:
  - do not include real secrets/tokens/credentials
  - do not touch non-module directories
  - do not invent table/field names; base everything on scanned SQL files
```

## Risk Summary
- HIGH: 7
- MEDIUM: 63
- LOW: 29

## Exact Findings (File/Line)
- [HIGH] 01_drop_tables.sql:6
  - sql: `BEGIN EXECUTE IMMEDIATE 'DROP TABLE PUBLIC_NOTICE_READ PURGE';`
  - why: Oracle PL/SQL anonymous exception block may fail on DM8 batch tools.
  - mitigation: Prefer DM8-native DROP TABLE IF EXISTS or isolated procedural execution.
- [HIGH] 01_drop_tables.sql:8
  - sql: `WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE;`
  - why: Oracle PL/SQL anonymous exception block may fail on DM8 batch tools.
  - mitigation: Prefer DM8-native DROP TABLE IF EXISTS or isolated procedural execution.
- [HIGH] 01_drop_tables.sql:11
  - sql: `/ BEGIN EXECUTE IMMEDIATE 'DROP TABLE PUBLIC_NOTICE_EXTERNAL_SOURCE PURGE';`
  - why: Oracle PL/SQL anonymous exception block may fail on DM8 batch tools.
  - mitigation: Prefer DM8-native DROP TABLE IF EXISTS or isolated procedural execution.
- [HIGH] 01_drop_tables.sql:16
  - sql: `/ BEGIN EXECUTE IMMEDIATE 'DROP TABLE PUBLIC_NOTICE_COVER PURGE';`
  - why: Oracle PL/SQL anonymous exception block may fail on DM8 batch tools.
  - mitigation: Prefer DM8-native DROP TABLE IF EXISTS or isolated procedural execution.
- [HIGH] 01_drop_tables.sql:21
  - sql: `/ BEGIN EXECUTE IMMEDIATE 'DROP TABLE PUBLIC_NOTICE_SCOPE PURGE';`
  - why: Oracle PL/SQL anonymous exception block may fail on DM8 batch tools.
  - mitigation: Prefer DM8-native DROP TABLE IF EXISTS or isolated procedural execution.
- [HIGH] 01_drop_tables.sql:26
  - sql: `/ BEGIN EXECUTE IMMEDIATE 'DROP TABLE PUBLIC_NOTICE PURGE';`
  - why: Oracle PL/SQL anonymous exception block may fail on DM8 batch tools.
  - mitigation: Prefer DM8-native DROP TABLE IF EXISTS or isolated procedural execution.
- [MEDIUM] 01_drop_tables.sql:31
  - sql: `/`
  - why: Slash delimiter is client-dependent and can break non-Oracle runners.
  - mitigation: Avoid procedure blocks or split scripts per statement runner.
- [MEDIUM] 02_create_public_notice.sql:6
  - sql: `NOTICE_ID VARCHAR2(32) NOT NULL,`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 02_create_public_notice.sql:7
  - sql: `TITLE VARCHAR2(200) NOT NULL,`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 02_create_public_notice.sql:9
  - sql: `PUBLISHER_TYPE VARCHAR2(32) NOT NULL,`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 02_create_public_notice.sql:11
  - sql: `PUBLISHER_ORG_ID VARCHAR2(32),`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 02_create_public_notice.sql:12
  - sql: `PUBLISHER_USER_ID VARCHAR2(32),`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 02_create_public_notice.sql:14
  - sql: `NOTICE_LEVEL VARCHAR2(32) NOT NULL,`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 02_create_public_notice.sql:16
  - sql: `DIST_ID VARCHAR2(32),`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 02_create_public_notice.sql:17
  - sql: `STREET_ID VARCHAR2(32),`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 02_create_public_notice.sql:18
  - sql: `COMMUNITY_ID VARCHAR2(32),`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 02_create_public_notice.sql:20
  - sql: `STATUS VARCHAR2(32) NOT NULL,`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 02_create_public_notice.sql:24
  - sql: `AUDIT_ORG_ID VARCHAR2(32),`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 02_create_public_notice.sql:25
  - sql: `AUDIT_USER_ID VARCHAR2(32),`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 02_create_public_notice.sql:26
  - sql: `AUDIT_TIME VARCHAR2(19),`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 02_create_public_notice.sql:27
  - sql: `AUDIT_COMMENT VARCHAR2(500),`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 02_create_public_notice.sql:29
  - sql: `PUBLISH_TIME VARCHAR2(19),`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 02_create_public_notice.sql:30
  - sql: `START_TIME VARCHAR2(19),`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 02_create_public_notice.sql:31
  - sql: `END_TIME VARCHAR2(19),`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 02_create_public_notice.sql:38
  - sql: `STORAGE_TYPE VARCHAR2(32) NOT NULL,`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 02_create_public_notice.sql:41
  - sql: `RELA_TABLE VARCHAR2(64),`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 02_create_public_notice.sql:42
  - sql: `RELA_TAB_ID VARCHAR2(64),`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 02_create_public_notice.sql:43
  - sql: `LINK_URL VARCHAR2(500),`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 02_create_public_notice.sql:46
  - sql: `CREATE_TIME VARCHAR2(19),`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 02_create_public_notice.sql:47
  - sql: `UPDATE_TIME VARCHAR2(19),`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 03_create_public_notice_scope.sql:7
  - sql: `NOTICE_ID   VARCHAR2(32) NOT NULL,`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 03_create_public_notice_scope.sql:8
  - sql: `SECT_ID     VARCHAR2(32) NOT NULL,`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 04_create_public_notice_cover.sql:7
  - sql: `NOTICE_ID   VARCHAR2(32) NOT NULL,`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 04_create_public_notice_cover.sql:8
  - sql: `COVER_TYPE  VARCHAR2(32) NOT NULL,  -- city / district / street / community / sect`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 04_create_public_notice_cover.sql:9
  - sql: `COVER_ID    VARCHAR2(32) NOT NULL,`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 05_create_public_notice_external_source.sql:7
  - sql: `SOURCE_CODE      VARCHAR2(64)  NOT NULL,`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 05_create_public_notice_external_source.sql:8
  - sql: `RELA_TABLE       VARCHAR2(64)  NOT NULL,`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 05_create_public_notice_external_source.sql:9
  - sql: `PK_COLUMN        VARCHAR2(64)  NOT NULL,`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 05_create_public_notice_external_source.sql:10
  - sql: `CONTENT_COLUMN   VARCHAR2(64)  NOT NULL,`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 05_create_public_notice_external_source.sql:13
  - sql: `REMARK           VARCHAR2(200),`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [LOW] 05_create_public_notice_external_source.sql:15
  - sql: `CREATE_TIME      DATE          DEFAULT CURRENT_TIMESTAMP,`
  - why: DATE default CURRENT_TIMESTAMP precision/implicit cast may differ by DB mode.
  - mitigation: Validate target DATE/TIMESTAMP semantic before production rollout.
- [LOW] 05_create_public_notice_external_source.sql:16
  - sql: `UPDATE_TIME      DATE          DEFAULT CURRENT_TIMESTAMP,`
  - why: DATE default CURRENT_TIMESTAMP precision/implicit cast may differ by DB mode.
  - mitigation: Validate target DATE/TIMESTAMP semantic before production rollout.
- [HIGH] 05_create_public_notice_external_source.sql:28
  - sql: `EXECUTE IMMEDIATE 'DROP TABLE PUBLIC_NOTICE_EXTERNAL_SOURCE PURGE';`
  - why: PURGE is Oracle-specific behavior and may be unsupported/unsafe in DM8 scripts.
  - mitigation: Use DROP TABLE IF EXISTS ... CASCADE in DM8 migration scripts.
- [MEDIUM] 05_create_public_notice_external_source.sql:33
  - sql: `/`
  - why: Slash delimiter is client-dependent and can break non-Oracle runners.
  - mitigation: Avoid procedure blocks or split scripts per statement runner.
- [MEDIUM] 07_create_public_notice_read.sql:6
  - sql: `ID VARCHAR2(32) NOT NULL,`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 07_create_public_notice_read.sql:7
  - sql: `NOTICE_ID VARCHAR2(32) NOT NULL,`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 07_create_public_notice_read.sql:8
  - sql: `USER_ID VARCHAR2(32) NOT NULL,`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 07_create_public_notice_read.sql:9
  - sql: `READ_TIME VARCHAR2(19),`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 07_create_public_notice_read.sql:10
  - sql: `CREATE_TIME VARCHAR2(19),`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [MEDIUM] 08_upgrade_from_legacy.sql:9
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD PUBLISHER_TYPE VARCHAR2(32);`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [LOW] 08_upgrade_from_legacy.sql:9
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD PUBLISHER_TYPE VARCHAR2(32);`
  - why: ALTER ADD without existence guard may fail in repeated runs.
  - mitigation: Run once in controlled batch or add pre-check SQL.
- [MEDIUM] 08_upgrade_from_legacy.sql:10
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD PUBLISHER_ORG_ID VARCHAR2(32);`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [LOW] 08_upgrade_from_legacy.sql:10
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD PUBLISHER_ORG_ID VARCHAR2(32);`
  - why: ALTER ADD without existence guard may fail in repeated runs.
  - mitigation: Run once in controlled batch or add pre-check SQL.
- [MEDIUM] 08_upgrade_from_legacy.sql:11
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD PUBLISHER_USER_ID VARCHAR2(32);`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [LOW] 08_upgrade_from_legacy.sql:11
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD PUBLISHER_USER_ID VARCHAR2(32);`
  - why: ALTER ADD without existence guard may fail in repeated runs.
  - mitigation: Run once in controlled batch or add pre-check SQL.
- [MEDIUM] 08_upgrade_from_legacy.sql:13
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD NOTICE_LEVEL VARCHAR2(32);`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [LOW] 08_upgrade_from_legacy.sql:13
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD NOTICE_LEVEL VARCHAR2(32);`
  - why: ALTER ADD without existence guard may fail in repeated runs.
  - mitigation: Run once in controlled batch or add pre-check SQL.
- [MEDIUM] 08_upgrade_from_legacy.sql:14
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD DIST_ID VARCHAR2(32);`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [LOW] 08_upgrade_from_legacy.sql:14
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD DIST_ID VARCHAR2(32);`
  - why: ALTER ADD without existence guard may fail in repeated runs.
  - mitigation: Run once in controlled batch or add pre-check SQL.
- [MEDIUM] 08_upgrade_from_legacy.sql:15
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD STREET_ID VARCHAR2(32);`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [LOW] 08_upgrade_from_legacy.sql:15
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD STREET_ID VARCHAR2(32);`
  - why: ALTER ADD without existence guard may fail in repeated runs.
  - mitigation: Run once in controlled batch or add pre-check SQL.
- [MEDIUM] 08_upgrade_from_legacy.sql:16
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD COMMUNITY_ID VARCHAR2(32);`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [LOW] 08_upgrade_from_legacy.sql:16
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD COMMUNITY_ID VARCHAR2(32);`
  - why: ALTER ADD without existence guard may fail in repeated runs.
  - mitigation: Run once in controlled batch or add pre-check SQL.
- [MEDIUM] 08_upgrade_from_legacy.sql:18
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD STATUS VARCHAR2(32);`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [LOW] 08_upgrade_from_legacy.sql:18
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD STATUS VARCHAR2(32);`
  - why: ALTER ADD without existence guard may fail in repeated runs.
  - mitigation: Run once in controlled batch or add pre-check SQL.
- [LOW] 08_upgrade_from_legacy.sql:19
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD AUDIT_REQUIRED CHAR(1);`
  - why: ALTER ADD without existence guard may fail in repeated runs.
  - mitigation: Run once in controlled batch or add pre-check SQL.
- [MEDIUM] 08_upgrade_from_legacy.sql:20
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD AUDIT_ORG_ID VARCHAR2(32);`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [LOW] 08_upgrade_from_legacy.sql:20
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD AUDIT_ORG_ID VARCHAR2(32);`
  - why: ALTER ADD without existence guard may fail in repeated runs.
  - mitigation: Run once in controlled batch or add pre-check SQL.
- [MEDIUM] 08_upgrade_from_legacy.sql:21
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD AUDIT_USER_ID VARCHAR2(32);`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [LOW] 08_upgrade_from_legacy.sql:21
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD AUDIT_USER_ID VARCHAR2(32);`
  - why: ALTER ADD without existence guard may fail in repeated runs.
  - mitigation: Run once in controlled batch or add pre-check SQL.
- [MEDIUM] 08_upgrade_from_legacy.sql:22
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD AUDIT_TIME VARCHAR2(19);`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [LOW] 08_upgrade_from_legacy.sql:22
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD AUDIT_TIME VARCHAR2(19);`
  - why: ALTER ADD without existence guard may fail in repeated runs.
  - mitigation: Run once in controlled batch or add pre-check SQL.
- [MEDIUM] 08_upgrade_from_legacy.sql:23
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD AUDIT_COMMENT VARCHAR2(500);`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [LOW] 08_upgrade_from_legacy.sql:23
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD AUDIT_COMMENT VARCHAR2(500);`
  - why: ALTER ADD without existence guard may fail in repeated runs.
  - mitigation: Run once in controlled batch or add pre-check SQL.
- [MEDIUM] 08_upgrade_from_legacy.sql:25
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD PUBLISH_TIME VARCHAR2(19);`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [LOW] 08_upgrade_from_legacy.sql:25
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD PUBLISH_TIME VARCHAR2(19);`
  - why: ALTER ADD without existence guard may fail in repeated runs.
  - mitigation: Run once in controlled batch or add pre-check SQL.
- [MEDIUM] 08_upgrade_from_legacy.sql:26
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD START_TIME VARCHAR2(19);`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [LOW] 08_upgrade_from_legacy.sql:26
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD START_TIME VARCHAR2(19);`
  - why: ALTER ADD without existence guard may fail in repeated runs.
  - mitigation: Run once in controlled batch or add pre-check SQL.
- [MEDIUM] 08_upgrade_from_legacy.sql:27
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD END_TIME VARCHAR2(19);`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [LOW] 08_upgrade_from_legacy.sql:27
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD END_TIME VARCHAR2(19);`
  - why: ALTER ADD without existence guard may fail in repeated runs.
  - mitigation: Run once in controlled batch or add pre-check SQL.
- [LOW] 08_upgrade_from_legacy.sql:29
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD TOP_FLAG CHAR(1);`
  - why: ALTER ADD without existence guard may fail in repeated runs.
  - mitigation: Run once in controlled batch or add pre-check SQL.
- [LOW] 08_upgrade_from_legacy.sql:30
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD PUBLIC_ACCESS CHAR(1);`
  - why: ALTER ADD without existence guard may fail in repeated runs.
  - mitigation: Run once in controlled batch or add pre-check SQL.
- [MEDIUM] 08_upgrade_from_legacy.sql:32
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD STORAGE_TYPE VARCHAR2(32);`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [LOW] 08_upgrade_from_legacy.sql:32
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD STORAGE_TYPE VARCHAR2(32);`
  - why: ALTER ADD without existence guard may fail in repeated runs.
  - mitigation: Run once in controlled batch or add pre-check SQL.
- [LOW] 08_upgrade_from_legacy.sql:33
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD GS_CONTENT CLOB;`
  - why: ALTER ADD without existence guard may fail in repeated runs.
  - mitigation: Run once in controlled batch or add pre-check SQL.
- [MEDIUM] 08_upgrade_from_legacy.sql:34
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD RELA_TABLE VARCHAR2(64);`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [LOW] 08_upgrade_from_legacy.sql:34
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD RELA_TABLE VARCHAR2(64);`
  - why: ALTER ADD without existence guard may fail in repeated runs.
  - mitigation: Run once in controlled batch or add pre-check SQL.
- [MEDIUM] 08_upgrade_from_legacy.sql:35
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD RELA_TAB_ID VARCHAR2(64);`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [LOW] 08_upgrade_from_legacy.sql:35
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD RELA_TAB_ID VARCHAR2(64);`
  - why: ALTER ADD without existence guard may fail in repeated runs.
  - mitigation: Run once in controlled batch or add pre-check SQL.
- [MEDIUM] 08_upgrade_from_legacy.sql:36
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD LINK_URL VARCHAR2(500);`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [LOW] 08_upgrade_from_legacy.sql:36
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD LINK_URL VARCHAR2(500);`
  - why: ALTER ADD without existence guard may fail in repeated runs.
  - mitigation: Run once in controlled batch or add pre-check SQL.
- [MEDIUM] 08_upgrade_from_legacy.sql:38
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD CREATE_TIME VARCHAR2(19);`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [LOW] 08_upgrade_from_legacy.sql:38
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD CREATE_TIME VARCHAR2(19);`
  - why: ALTER ADD without existence guard may fail in repeated runs.
  - mitigation: Run once in controlled batch or add pre-check SQL.
- [MEDIUM] 08_upgrade_from_legacy.sql:39
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD UPDATE_TIME VARCHAR2(19);`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [LOW] 08_upgrade_from_legacy.sql:39
  - sql: `ALTER TABLE PUBLIC_NOTICE ADD UPDATE_TIME VARCHAR2(19);`
  - why: ALTER ADD without existence guard may fail in repeated runs.
  - mitigation: Run once in controlled batch or add pre-check SQL.
- [MEDIUM] 08_upgrade_from_legacy.sql:42
  - sql: `ALTER TABLE PUBLIC_NOTICE_READ ADD ID VARCHAR2(32);`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [LOW] 08_upgrade_from_legacy.sql:42
  - sql: `ALTER TABLE PUBLIC_NOTICE_READ ADD ID VARCHAR2(32);`
  - why: ALTER ADD without existence guard may fail in repeated runs.
  - mitigation: Run once in controlled batch or add pre-check SQL.
- [MEDIUM] 08_upgrade_from_legacy.sql:43
  - sql: `ALTER TABLE PUBLIC_NOTICE_READ ADD CREATE_TIME VARCHAR2(19);`
  - why: VARCHAR2 is Oracle type alias; DM8 compatibility depends on settings.
  - mitigation: Normalize to VARCHAR for deterministic execution.
- [LOW] 08_upgrade_from_legacy.sql:43
  - sql: `ALTER TABLE PUBLIC_NOTICE_READ ADD CREATE_TIME VARCHAR2(19);`
  - why: ALTER ADD without existence guard may fail in repeated runs.
  - mitigation: Run once in controlled batch or add pre-check SQL.

```

## step1/A2_oracle_feature_map.md

```md
# A2_oracle_feature_map

- context_id: ctx-3a70562661bc
- trace_id: trace-c4d7acea934f4bbbb5a8979a1de7051b
- input_artifact_refs: ["A1"]

## Oracle Feature Frequency and Locations

| Feature | Count | Example locations | DM8 handling |
|---|---:|---|---|
| `VARCHAR2` | 66 | `02_create_public_notice.sql:6`, `08_upgrade_from_legacy.sql:9`, `07_create_public_notice_read.sql:6` | Convert to `VARCHAR` for deterministic portability |
| `EXECUTE IMMEDIATE` | 6 | `01_drop_tables.sql:6/11/16/21/26`, `05_create_public_notice_external_source.sql:28` | Replace with DM8 `DROP TABLE IF EXISTS ... CASCADE` |
| `WHEN OTHERS` | 6 | `01_drop_tables.sql:8/13/18/23/28`, `05_create_public_notice_external_source.sql:30` | Remove Oracle exception blocks from migration scripts |
| `SQLCODE != -942` | 6 | `01_drop_tables.sql:8/13/18/23/28`, `05_create_public_notice_external_source.sql:31` | Use existence check / IF EXISTS semantics instead |
| `PURGE` | 6 | `01_drop_tables.sql:6/11/16/21/26`, `05_create_public_notice_external_source.sql:28` | Remove `PURGE`; DM8 does not require Oracle recycle-bin syntax |
| Slash delimiter `/` | 6 | `01_drop_tables.sql:11/16/21/26/31`, `05_create_public_notice_external_source.sql:33` | Remove client-dependent delimiter blocks |
| `ROWNUM` | 0 | not found | No action |
| `NVL(...)` | 0 | not found | No action |
| `CONNECT BY` | 0 | not found | No action |
| `MERGE` | 0 | not found | No action |
| `SEQUENCE` | 0 | not found | No action |
| `TRIGGER` | 0 | not found | No action |
| `PACKAGE` | 0 | not found | No action |
| `DUAL` | 0 | not found | No action |

## Mapping Notes
1. 本批 SQL 的主要迁移成本集中在 Oracle 方言 DDL/异常控制块与 `VARCHAR2` 类型替换。
2. 未发现复杂 Oracle 查询特性（`CONNECT BY`/`ROWNUM`/`MERGE`），因此迁移风险以 DDL 可执行性为主。
3. `10_menu_and_role_config.sql` 主要为业务配置 DML，本次未发现 Oracle 专有函数依赖。

```

## step2/A1_dm8_sql_merged.sql

```sql
-- >>> FILE: 01_drop_tables.sql
-- ================================
-- 统一 DROP（DM8 版 IF EXISTS）
-- 01_drop_tables.sql
-- 公示公告模块 - 安全删除表
-- ================================
DROP TABLE IF EXISTS PUBLIC_NOTICE_READ CASCADE;
DROP TABLE IF EXISTS PUBLIC_NOTICE_EXTERNAL_SOURCE CASCADE;
DROP TABLE IF EXISTS PUBLIC_NOTICE_COVER CASCADE;
DROP TABLE IF EXISTS PUBLIC_NOTICE_SCOPE CASCADE;
DROP TABLE IF EXISTS PUBLIC_NOTICE CASCADE;

-- >>> FILE: 02_create_public_notice.sql
-- ================================
-- 02_create_public_notice.sql
-- 公示公告主表
-- ================================
CREATE TABLE PUBLIC_NOTICE (
    NOTICE_ID VARCHAR(32) NOT NULL,
    TITLE VARCHAR(200) NOT NULL,
    -- 发布主体
    PUBLISHER_TYPE VARCHAR(32) NOT NULL,
    -- city_bureau / district_bureau / street / community / property_company / owner_committee
    PUBLISHER_ORG_ID VARCHAR(32),
    PUBLISHER_USER_ID VARCHAR(32),
    -- 公告级别与区域
    NOTICE_LEVEL VARCHAR(32) NOT NULL,
    -- city / district / street / community / sect
    DIST_ID VARCHAR(32),
    STREET_ID VARCHAR(32),
    COMMUNITY_ID VARCHAR(32),
    -- 状态流转
    STATUS VARCHAR(32) NOT NULL,
    -- draft / submitted / approved / rejected / published / canceled
    AUDIT_REQUIRED CHAR(1) DEFAULT 'N',
    -- Y/N
    AUDIT_ORG_ID VARCHAR(32),
    AUDIT_USER_ID VARCHAR(32),
    AUDIT_TIME VARCHAR(19),
    AUDIT_COMMENT VARCHAR(500),
    -- 发布信息
    PUBLISH_TIME VARCHAR(19),
    START_TIME VARCHAR(19),
    END_TIME VARCHAR(19),
    -- 展示控制
    TOP_FLAG CHAR(1) DEFAULT 'N',
    -- Y/N
    PUBLIC_ACCESS CHAR(1) DEFAULT 'N',
    -- Y/N（无需认证）
    -- 内容存储（三选一）
    STORAGE_TYPE VARCHAR(32) NOT NULL,
    -- inline / external_table / external_link
    GS_CONTENT CLOB,
    RELA_TABLE VARCHAR(64),
    RELA_TAB_ID VARCHAR(64),
    LINK_URL VARCHAR(500),
    -- 通用字段
    DELETED_FLAG CHAR(1) DEFAULT 'N',
    CREATE_TIME VARCHAR(19),
    UPDATE_TIME VARCHAR(19),
    CONSTRAINT PK_PUBLIC_NOTICE PRIMARY KEY (NOTICE_ID)
);

-- >>> FILE: 03_create_public_notice_scope.sql
-- ================================
-- 03_create_public_notice_scope.sql
-- 小区级公告范围表
-- ================================

CREATE TABLE PUBLIC_NOTICE_SCOPE (
                                     NOTICE_ID   VARCHAR(32) NOT NULL,
                                     SECT_ID     VARCHAR(32) NOT NULL,

                                     CONSTRAINT PK_PUBLIC_NOTICE_SCOPE PRIMARY KEY (NOTICE_ID, SECT_ID)
);

-- >>> FILE: 04_create_public_notice_cover.sql
-- ================================
-- 04_create_public_notice_cover.sql
-- 公告可见性索引表（cover）
-- ================================

CREATE TABLE PUBLIC_NOTICE_COVER (
                                     NOTICE_ID   VARCHAR(32) NOT NULL,
                                     COVER_TYPE  VARCHAR(32) NOT NULL,  -- city / district / street / community / sect
                                     COVER_ID    VARCHAR(32) NOT NULL,

                                     CONSTRAINT PK_PUBLIC_NOTICE_COVER PRIMARY KEY (NOTICE_ID, COVER_TYPE, COVER_ID)
);

-- >>> FILE: 05_create_public_notice_external_source.sql
-- =========================================
-- 05_create_public_notice_external_source.sql
-- 外部内容表白名单
-- =========================================

CREATE TABLE PUBLIC_NOTICE_EXTERNAL_SOURCE (
                                               SOURCE_CODE      VARCHAR(64)  NOT NULL,
                                               RELA_TABLE       VARCHAR(64)  NOT NULL,
                                               PK_COLUMN        VARCHAR(64)  NOT NULL,
                                               CONTENT_COLUMN   VARCHAR(64)  NOT NULL,

                                               ENABLED_FLAG     CHAR(1)       DEFAULT 'Y',
                                               REMARK           VARCHAR(200),

                                               CREATE_TIME      DATE          DEFAULT CURRENT_TIMESTAMP,
                                               UPDATE_TIME      DATE          DEFAULT CURRENT_TIMESTAMP,

                                               CONSTRAINT PK_PUBLIC_NOTICE_EXTERNAL_SOURCE PRIMARY KEY (SOURCE_CODE),
                                               CONSTRAINT UK_PUBLIC_NOTICE_EXT_TABLE UNIQUE (RELA_TABLE)
);

-- =========================================

-- >>> FILE: 06_create_index.sql
-- ================================
-- 06_create_index.sql
-- 公示公告模块性能索引
-- Oracle/MySQL 兼容
-- ================================
-- ===========================================
-- PUBLIC_NOTICE 主表索引
-- ===========================================
-- 状态筛选（管理列表/审核列表常用）
CREATE INDEX IDX_PN_STATUS ON PUBLIC_NOTICE (STATUS);
-- 发布时间（门户列表排序）
CREATE INDEX IDX_PN_PUBLISH_TIME ON PUBLIC_NOTICE (PUBLISH_TIME);
-- 审核组织（审核待办查询）
CREATE INDEX IDX_PN_AUDIT_ORG ON PUBLIC_NOTICE (AUDIT_ORG_ID);
-- 发布组织（按组织查询）
CREATE INDEX IDX_PN_PUBLISHER_ORG ON PUBLIC_NOTICE (PUBLISHER_ORG_ID);
-- 区域索引（级联查询）
CREATE INDEX IDX_PN_COMMUNITY ON PUBLIC_NOTICE (COMMUNITY_ID);
CREATE INDEX IDX_PN_STREET ON PUBLIC_NOTICE (STREET_ID);
CREATE INDEX IDX_PN_DIST ON PUBLIC_NOTICE (DIST_ID);
-- 复合索引：状态 + 审核组织（审核待办优化）
CREATE INDEX IDX_PN_STATUS_AUDIT ON PUBLIC_NOTICE (STATUS, AUDIT_ORG_ID);
-- 时效判断
CREATE INDEX IDX_PN_TIME_RANGE ON PUBLIC_NOTICE (START_TIME, END_TIME);
-- ===========================================
-- PUBLIC_NOTICE_SCOPE 范围表索引
-- ===========================================
-- 按小区查询公告
CREATE INDEX IDX_PNS_SECT ON PUBLIC_NOTICE_SCOPE (SECT_ID);
-- ===========================================
-- PUBLIC_NOTICE_COVER 覆盖表索引
-- ===========================================
-- 覆盖查询（类型 + ID）
CREATE INDEX IDX_PNC_COVER ON PUBLIC_NOTICE_COVER (COVER_TYPE, COVER_ID);
-- 按公告ID查覆盖范围
CREATE INDEX IDX_PNC_NOTICE ON PUBLIC_NOTICE_COVER (NOTICE_ID);
-- ===========================================
-- PUBLIC_NOTICE_READ 已读表索引
-- 注：唯一索引已在 07_create_public_notice_read.sql 中创建
-- ===========================================
-- 以下索引已在建表脚本中创建，此处仅作文档说明
-- CREATE UNIQUE INDEX UNQ_PNR_NOTICE_USER ON PUBLIC_NOTICE_READ (NOTICE_ID, USER_ID);
-- CREATE INDEX IDX_PNR_USER ON PUBLIC_NOTICE_READ (USER_ID);
-- CREATE INDEX IDX_PNR_NOTICE ON PUBLIC_NOTICE_READ (NOTICE_ID);

-- >>> FILE: 07_create_public_notice_read.sql
-- ================================
-- 07_create_public_notice_read.sql
-- 公告已读记录表
-- ================================
CREATE TABLE PUBLIC_NOTICE_READ (
    ID VARCHAR(32) NOT NULL,
    NOTICE_ID VARCHAR(32) NOT NULL,
    USER_ID VARCHAR(32) NOT NULL,
    READ_TIME VARCHAR(19),
    CREATE_TIME VARCHAR(19),
    CONSTRAINT PK_PUBLIC_NOTICE_READ PRIMARY KEY (ID)
);
-- 唯一约束：同一用户只能对同一公告标记一次已读
CREATE UNIQUE INDEX UNQ_PNR_NOTICE_USER ON PUBLIC_NOTICE_READ (NOTICE_ID, USER_ID);
-- 性能索引
CREATE INDEX IDX_PNR_USER ON PUBLIC_NOTICE_READ (USER_ID);
CREATE INDEX IDX_PNR_NOTICE ON PUBLIC_NOTICE_READ (NOTICE_ID);

-- >>> FILE: 08_upgrade_from_legacy.sql
-- ================================
-- 08_upgrade_from_legacy.sql
-- 兼容升级脚本：将旧版最小字段表升级为公告模块所需字段
-- 适用：Oracle/MySQL
-- 注意：若列已存在，请手动删除对应语句再执行
-- ================================

-- PUBLIC_NOTICE 补充缺失字段
ALTER TABLE PUBLIC_NOTICE ADD PUBLISHER_TYPE VARCHAR(32);
ALTER TABLE PUBLIC_NOTICE ADD PUBLISHER_ORG_ID VARCHAR(32);
ALTER TABLE PUBLIC_NOTICE ADD PUBLISHER_USER_ID VARCHAR(32);

ALTER TABLE PUBLIC_NOTICE ADD NOTICE_LEVEL VARCHAR(32);
ALTER TABLE PUBLIC_NOTICE ADD DIST_ID VARCHAR(32);
ALTER TABLE PUBLIC_NOTICE ADD STREET_ID VARCHAR(32);
ALTER TABLE PUBLIC_NOTICE ADD COMMUNITY_ID VARCHAR(32);

ALTER TABLE PUBLIC_NOTICE ADD STATUS VARCHAR(32);
ALTER TABLE PUBLIC_NOTICE ADD AUDIT_REQUIRED CHAR(1);
ALTER TABLE PUBLIC_NOTICE ADD AUDIT_ORG_ID VARCHAR(32);
ALTER TABLE PUBLIC_NOTICE ADD AUDIT_USER_ID VARCHAR(32);
ALTER TABLE PUBLIC_NOTICE ADD AUDIT_TIME VARCHAR(19);
ALTER TABLE PUBLIC_NOTICE ADD AUDIT_COMMENT VARCHAR(500);

ALTER TABLE PUBLIC_NOTICE ADD PUBLISH_TIME VARCHAR(19);
ALTER TABLE PUBLIC_NOTICE ADD START_TIME VARCHAR(19);
ALTER TABLE PUBLIC_NOTICE ADD END_TIME VARCHAR(19);

ALTER TABLE PUBLIC_NOTICE ADD TOP_FLAG CHAR(1);
ALTER TABLE PUBLIC_NOTICE ADD PUBLIC_ACCESS CHAR(1);

ALTER TABLE PUBLIC_NOTICE ADD STORAGE_TYPE VARCHAR(32);
ALTER TABLE PUBLIC_NOTICE ADD GS_CONTENT CLOB;
ALTER TABLE PUBLIC_NOTICE ADD RELA_TABLE VARCHAR(64);
ALTER TABLE PUBLIC_NOTICE ADD RELA_TAB_ID VARCHAR(64);
ALTER TABLE PUBLIC_NOTICE ADD LINK_URL VARCHAR(500);

ALTER TABLE PUBLIC_NOTICE ADD CREATE_TIME VARCHAR(19);
ALTER TABLE PUBLIC_NOTICE ADD UPDATE_TIME VARCHAR(19);

-- PUBLIC_NOTICE_READ 补充缺失字段
ALTER TABLE PUBLIC_NOTICE_READ ADD ID VARCHAR(32);
ALTER TABLE PUBLIC_NOTICE_READ ADD CREATE_TIME VARCHAR(19);

-- 如需索引，请执行 06_create_index.sql

-- >>> FILE: 10_menu_and_role_config.sql
-- =============================================================================
-- 公示公告模块菜单和权限配置
-- 执行顺序：先执行本文件，再验证菜单显示
-- 执行时间：2026-02-05
-- =============================================================================
-- =============================================================================
-- 第一部分：菜单配置
-- =============================================================================
-- 1. 公告管理（发布入口）
INSERT INTO SYS_MENU_INFO (
        MENU_ID,
        CLIENT_NO,
        MENU_NAME,
        PARENT_ID,
        MENU_URL,
        MENU_ICON,
        OPER_USER,
        MENU_LEVEL,
        TM_SMP,
        SORT_NUM,
        IS_HOME,
        HOME_ICON
    )
VALUES (
        30837,
        'HYJG_CLIENT',
        '公告管理',
        30836,
        '/pages/backstage/notice/index.xhtml',
        'fa-edit',
        '10000',
        2,
        '20260205',
        1,
        0,
        ''
    );
-- 2. 公告审核（社区审核入口）
INSERT INTO SYS_MENU_INFO (
        MENU_ID,
        CLIENT_NO,
        MENU_NAME,
        PARENT_ID,
        MENU_URL,
        MENU_ICON,
        OPER_USER,
        MENU_LEVEL,
        TM_SMP,
        SORT_NUM,
        IS_HOME,
        HOME_ICON
    )
VALUES (
        30838,
        'HYJG_CLIENT',
        '公告审核',
        30836,
        '/pages/backstage/notice/audit_index.xhtml',
        'fa-check-square-o',
        '10000',
        2,
        '20260205',
        2,
        0,
        ''
    );
-- =============================================================================
-- 第二部分：角色菜单权限配置
-- =============================================================================
-- 行业监管-管理员 (40210) - 全部菜单
INSERT INTO SYS_ROLE_MENU (ROLE_ID, MENU_ID, TM_SMP)
VALUES (40210, 30836, '20260205');
INSERT INTO SYS_ROLE_MENU (ROLE_ID, MENU_ID, TM_SMP)
VALUES (40210, 30837, '20260205');
INSERT INTO SYS_ROLE_MENU (ROLE_ID, MENU_ID, TM_SMP)
VALUES (40210, 30838, '20260205');
-- 行业监管-市局 (40211) - 公告管理
INSERT INTO SYS_ROLE_MENU (ROLE_ID, MENU_ID, TM_SMP)
VALUES (40211, 30836, '20260205');
INSERT INTO SYS_ROLE_MENU (ROLE_ID, MENU_ID, TM_SMP)
VALUES (40211, 30837, '20260205');
-- 行业监管-区局 (40212) - 公告管理
INSERT INTO SYS_ROLE_MENU (ROLE_ID, MENU_ID, TM_SMP)
VALUES (40212, 30836, '20260205');
INSERT INTO SYS_ROLE_MENU (ROLE_ID, MENU_ID, TM_SMP)
VALUES (40212, 30837, '20260205');
-- 行业监管-街道 (40213) - 公告管理
INSERT INTO SYS_ROLE_MENU (ROLE_ID, MENU_ID, TM_SMP)
VALUES (40213, 30836, '20260205');
INSERT INTO SYS_ROLE_MENU (ROLE_ID, MENU_ID, TM_SMP)
VALUES (40213, 30837, '20260205');
-- 行业监管-社区 (40214) - 公告管理 + 公告审核
INSERT INTO SYS_ROLE_MENU (ROLE_ID, MENU_ID, TM_SMP)
VALUES (40214, 30836, '20260205');
INSERT INTO SYS_ROLE_MENU (ROLE_ID, MENU_ID, TM_SMP)
VALUES (40214, 30837, '20260205');
INSERT INTO SYS_ROLE_MENU (ROLE_ID, MENU_ID, TM_SMP)
VALUES (40214, 30838, '20260205');
-- 行业监管-业委会 (40230) - 公告管理
INSERT INTO SYS_ROLE_MENU (ROLE_ID, MENU_ID, TM_SMP)
VALUES (40230, 30836, '20260205');
INSERT INTO SYS_ROLE_MENU (ROLE_ID, MENU_ID, TM_SMP)
VALUES (40230, 30837, '20260205');
-- 行业监管-物业公司 (40240) - 公告管理
INSERT INTO SYS_ROLE_MENU (ROLE_ID, MENU_ID, TM_SMP)
VALUES (40240, 30836, '20260205');
INSERT INTO SYS_ROLE_MENU (ROLE_ID, MENU_ID, TM_SMP)
VALUES (40240, 30837, '20260205');
-- 行业监管-项目经理 (40241) - 公告管理
INSERT INTO SYS_ROLE_MENU (ROLE_ID, MENU_ID, TM_SMP)
VALUES (40241, 30836, '20260205');
INSERT INTO SYS_ROLE_MENU (ROLE_ID, MENU_ID, TM_SMP)
VALUES (40241, 30837, '20260205');
COMMIT;

```

## step2/A2_conversion_report.md

```md
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

```

## step2/A3_manual_todo_list.md

```md
# A3_manual_todo_list

- context_id: ctx-3a70562661bc
- trace_id: trace-c4d7acea934f4bbbb5a8979a1de7051b
- input_artifact_refs: ["A1"]

## Manual Confirmation Items (Actionable)

1. **Drop strategy confirmation**
- check: 是否允许在目标环境执行 `DROP TABLE IF EXISTS ... CASCADE`（仅全量重建场景）。
- action: 若为增量升级，禁用 drop 段，仅执行 create/alter 段。

2. **Date/Timestamp semantics**
- check: 业务字段使用 `VARCHAR(19)` 保存时间戳是否继续保留；`DATE DEFAULT CURRENT_TIMESTAMP` 是否符合期望精度。
- action: 在 DM8 测试库执行插入样例，确认显示与比较逻辑不变。

3. **Index create timing**
- check: 大批量导入前是否延后二级索引创建。
- action: 如果有数据回灌，采用“先表后数后索引”策略降低锁等待。

4. **Legacy upgrade gating**
- check: `08_upgrade_from_legacy.sql` 是否适用于当前库版本。
- action: 先比对目标库是否已具备新增列，避免重复 `ALTER TABLE ADD` 失败。

5. **Config DML safety window**
- check: `10_menu_and_role_config.sql` 是否在变更窗口执行并已审批。
- action: 以单独事务执行并保留回滚脚本。

6. **Execution runner compatibility**
- check: 执行工具是否按分号分句，避免 Oracle 风格 `/` 分隔残留干扰。
- action: 统一使用转换后的合并脚本 `A1_dm8_sql_merged.sql`。

```

## step3/A1_index_review_report.md

```md
# A1_index_review_report

- context_id: ctx-3a70562661bc
- trace_id: trace-c4d7acea934f4bbbb5a8979a1de7051b
- input_artifact_refs: ["A2"]

## Index Inventory
- IDX_PN_STATUS ON PUBLIC_NOTICE (STATUS)
- IDX_PN_PUBLISH_TIME ON PUBLIC_NOTICE (PUBLISH_TIME)
- IDX_PN_AUDIT_ORG ON PUBLIC_NOTICE (AUDIT_ORG_ID)
- IDX_PN_PUBLISHER_ORG ON PUBLIC_NOTICE (PUBLISHER_ORG_ID)
- IDX_PN_COMMUNITY ON PUBLIC_NOTICE (COMMUNITY_ID)
- IDX_PN_STREET ON PUBLIC_NOTICE (STREET_ID)
- IDX_PN_DIST ON PUBLIC_NOTICE (DIST_ID)
- IDX_PN_STATUS_AUDIT ON PUBLIC_NOTICE (STATUS, AUDIT_ORG_ID)
- IDX_PN_TIME_RANGE ON PUBLIC_NOTICE (START_TIME, END_TIME)
- IDX_PNS_SECT ON PUBLIC_NOTICE_SCOPE (SECT_ID)
- IDX_PNC_COVER ON PUBLIC_NOTICE_COVER (COVER_TYPE, COVER_ID)
- IDX_PNC_NOTICE ON PUBLIC_NOTICE_COVER (NOTICE_ID)
- UNQ_PNR_NOTICE_USER ON PUBLIC_NOTICE_READ (NOTICE_ID, USER_ID)
- IDX_PNR_USER ON PUBLIC_NOTICE_READ (USER_ID)
- IDX_PNR_NOTICE ON PUBLIC_NOTICE_READ (NOTICE_ID)

## Findings
- [MEDIUM] `IDX_PN_STATUS` may overlap with composite `IDX_PN_STATUS_AUDIT` for some query paths.
  - reason: left-prefix access may already cover STATUS-only lookups in many plans.
  - impact: extra write amplification during insert/update on `PUBLIC_NOTICE`.
  - mitigation: keep both initially, then validate with DM8 execution plan and remove redundant one if confirmed.
- [MEDIUM] Multiple single-column regional indexes (`IDX_PN_COMMUNITY`,`IDX_PN_STREET`,`IDX_PN_DIST`) increase maintenance cost.
  - reason: each DML touches more index pages.
  - impact: slower bulk migration writes.
  - mitigation: delay non-critical index creation until after bulk load where feasible.
- [LOW] `IDX_PNR_NOTICE` may be partially covered by unique index `UNQ_PNR_NOTICE_USER` depending query filters.
  - reason: leftmost prefix can satisfy some NOTICE_ID queries.
  - impact: potential index redundancy.
  - mitigation: observe DM8 workload and retain only if hit ratio proves value.

```

## step3/A2_perf_and_lock_risks.md

```md
# A2_perf_and_lock_risks

- context_id: ctx-3a70562661bc
- trace_id: trace-c4d7acea934f4bbbb5a8979a1de7051b
- input_artifact_refs: ["A2"]

## Execution-order and Lock Risks

1. **Metadata lock risk (MEDIUM)**
- why: `ALTER TABLE ... ADD ...`（`08_upgrade_from_legacy.sql`）会持有元数据锁。
- impact: 并发业务会话可能等待，迁移窗口被拉长。
- mitigation: 低峰执行，单语句超时与重试策略，必要时拆批执行。
- rollback point: 语句级失败立即停止，回到批次边界。

2. **Index build amplification (MEDIUM)**
- why: `PUBLIC_NOTICE` 上多索引连续创建会放大 IO 与锁持有时间。
- impact: 大表场景可能出现长事务/锁等待。
- mitigation: 数据装载后再建非核心索引；按优先级分批建索引。
- rollback point: 每批索引创建后提交并记录完成点。

3. **Config DML contention (LOW)**
- why: `SYS_MENU_INFO`/`SYS_ROLE_MENU` 写入与权限管控耦合。
- impact: 可能触发重复键或权限拒绝导致批次失败。
- mitigation: 独立事务窗口执行，先做存在性检查。
- rollback point: 仅回滚当前 DML 事务，不影响已完成 DDL 批次。

4. **Schema drift risk (MEDIUM)**
- why: 目标库若已部分升级，再次执行同名 `ALTER` 可能报错。
- impact: 批次中断，需人工确认状态。
- mitigation: 执行前做对象存在检查并生成差异单。
- rollback point: 升级前全库备份 + 批次断点清单。

```

## step3/A3_handoff_refs.md

```md
# A3_handoff_refs

- context_id: ctx-3a70562661bc
- trace_id: trace-c4d7acea934f4bbbb5a8979a1de7051b

## Step4 Required References
- A2 => Step2.A2_conversion_report.md + Step2.A3_manual_todo_list.md（转换差异与人工确认项）
- A3 => Step3.A1_index_review_report.md + Step3.A2_perf_and_lock_risks.md（索引与性能/锁风险）

## Input Artifact Mapping for Step4
- input_artifact_refs: ["A2", "A3"]

```

## step4/A1_release_migration_runbook.md

```md
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

```

## step4/A2_verification_checklist.md

```md
# A2_verification_checklist

- context_id: ctx-3a70562661bc
- trace_id: trace-c4d7acea934f4bbbb5a8979a1de7051b

## Structural Verification
- [ ] Tables created: PUBLIC_NOTICE, PUBLIC_NOTICE_SCOPE, PUBLIC_NOTICE_COVER, PUBLIC_NOTICE_EXTERNAL_SOURCE, PUBLIC_NOTICE_READ
- [ ] Primary keys and unique constraints exist as defined
- [ ] Indexes from 06_create_index.sql exist

## Data/Config Verification
- [ ] `SYS_MENU_INFO` rows for 30837/30838 inserted as expected
- [ ] `SYS_ROLE_MENU` mappings inserted without duplication errors
- [ ] No unauthorized object outside module scope changed

## Acceptance Mapping
- [ ] A1 portability audit reviewed
- [ ] A2 converted SQL executable in DM8 dry run
- [ ] A3 performance/index risks accepted or mitigated
- [ ] Runbook and rollback plan approved

```

## step4/A3_final_delivery_manifest.md

```md
# A3_final_delivery_manifest

- context_id: ctx-3a70562661bc
- trace_id: trace-c4d7acea934f4bbbb5a8979a1de7051b
- generated_at: 2026-02-09T09:58:00Z
- module_path: /Users/dwight/Downloads/HongzhiTechnology_SvnRepository/Project/xiangyang/zhihuiwuye/4coding/xywygl/src/main/java/com/indihx/notice

## Delivery Artifacts
- step1/A1_portability_risk_report.md
- step1/A2_oracle_feature_map.md
- step1/A2_portability_patch_notes.md
- step2/A1_dm8_sql_merged.sql
- step2/A2_conversion_report.md
- step2/A3_manual_todo_list.md
- step3/A1_index_review_report.md
- step3/A2_perf_and_lock_risks.md
- step3/A2_perf_risk_notes.md
- step3/A3_handoff_refs.md
- step4/A1_release_migration_runbook.md
- step4/A2_verification_checklist.md
- step4/A3_final_delivery_manifest.md

## Source SQL Files
- /Users/dwight/Downloads/HongzhiTechnology_SvnRepository/Project/xiangyang/zhihuiwuye/4coding/xywygl/src/main/java/com/indihx/notice/sql/01_drop_tables.sql
- /Users/dwight/Downloads/HongzhiTechnology_SvnRepository/Project/xiangyang/zhihuiwuye/4coding/xywygl/src/main/java/com/indihx/notice/sql/02_create_public_notice.sql
- /Users/dwight/Downloads/HongzhiTechnology_SvnRepository/Project/xiangyang/zhihuiwuye/4coding/xywygl/src/main/java/com/indihx/notice/sql/03_create_public_notice_scope.sql
- /Users/dwight/Downloads/HongzhiTechnology_SvnRepository/Project/xiangyang/zhihuiwuye/4coding/xywygl/src/main/java/com/indihx/notice/sql/04_create_public_notice_cover.sql
- /Users/dwight/Downloads/HongzhiTechnology_SvnRepository/Project/xiangyang/zhihuiwuye/4coding/xywygl/src/main/java/com/indihx/notice/sql/05_create_public_notice_external_source.sql
- /Users/dwight/Downloads/HongzhiTechnology_SvnRepository/Project/xiangyang/zhihuiwuye/4coding/xywygl/src/main/java/com/indihx/notice/sql/06_create_index.sql
- /Users/dwight/Downloads/HongzhiTechnology_SvnRepository/Project/xiangyang/zhihuiwuye/4coding/xywygl/src/main/java/com/indihx/notice/sql/07_create_public_notice_read.sql
- /Users/dwight/Downloads/HongzhiTechnology_SvnRepository/Project/xiangyang/zhihuiwuye/4coding/xywygl/src/main/java/com/indihx/notice/sql/08_upgrade_from_legacy.sql
- /Users/dwight/Downloads/HongzhiTechnology_SvnRepository/Project/xiangyang/zhihuiwuye/4coding/xywygl/src/main/java/com/indihx/notice/sql/10_menu_and_role_config.sql

```

