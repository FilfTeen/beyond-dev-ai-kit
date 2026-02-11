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
