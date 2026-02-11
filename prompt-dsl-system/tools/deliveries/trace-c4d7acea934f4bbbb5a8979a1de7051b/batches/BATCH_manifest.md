# BATCH_manifest

- context_id: ctx-3a70562661bc
- trace_id: trace-c4d7acea934f4bbbb5a8979a1de7051b

## Batch 列表与内容映射

### Batch1_drop_optional.sql
- 来源文件：`01_drop_tables.sql`
- 段落：破坏性 DDL（删除 `PUBLIC_NOTICE*` 相关表）
- 风险点：数据不可恢复（除非有备份）
- 回滚点：执行前完整备份；执行后只能通过备份回灌
- 幂等性：可重复执行（`DROP TABLE IF EXISTS`）
- 不可逆性：是（业务数据删除）

### Batch2_core_schema.sql
- 来源文件：`02/03/04/05/07` 建表 + `06` 索引
- 段落：核心结构创建（主表、范围表、覆盖表、外部源表、已读表、性能索引）
- 风险点：对象已存在会报错；索引重复创建会报错
- 回滚点：回退到 Batch1 再重建，或逐对象 DROP 回滚
- 幂等性：不可直接重复执行（需要对象不存在）
- 不可逆性：否（结构可删可重建）

### Batch3_upgrade_and_config.sql
- 来源文件：`08_upgrade_from_legacy.sql` + `10_menu_and_role_config.sql`
- 段落：增量列补齐 + 菜单角色配置
- 风险点：重复 `ALTER TABLE ADD`/`INSERT` 可能失败或产生重复数据
- 回滚点：
  - 升级列：按变更清单手工回滚（高风险，通常不建议生产回删列）
  - 配置：按 `MENU_ID` 与 `ROLE_ID/MENU_ID` 精确删除
- 幂等性：默认不可重复执行
- 不可逆性：部分不可逆（列变更通常不建议回退）

### Batch4_verification.sql
- 来源依据：`step4/A2_verification_checklist.md`
- 段落：对象存在性、索引存在性、数量核对、配置重复核查
- 风险点：只读查询，无写入风险
- 回滚点：不需要
- 幂等性：可重复执行
- 不可逆性：否

### Batch_all_merged.sql
- 来源文件：`01 -> 02 -> 03 -> 04 -> 05 -> 07 -> 06 -> 08 -> 10`
- 用途：一键执行完整交付脚本（已清理 Oracle 单独 `/` 分隔符）
- 风险点：包含 Drop/DDL/DML，需按环境慎用
- 回滚点：按 Batch1/2/3 的回滚策略执行
- 幂等性：不可直接重复执行（受 DDL/DML 影响）
- 不可逆性：包含不可逆步骤（Drop）
