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
