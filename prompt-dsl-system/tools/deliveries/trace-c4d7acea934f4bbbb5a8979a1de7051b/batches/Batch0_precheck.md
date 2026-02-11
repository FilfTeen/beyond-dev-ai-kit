# Batch0_precheck

- context_id: ctx-3a70562661bc
- trace_id: trace-c4d7acea934f4bbbb5a8979a1de7051b
- source_files: 01/02/03/04/05/06/07/08/10

## 执行前确认
1. 目标数据库为 DM8，客户端编码 UTF-8。
2. 执行账号具备 DDL/DML 权限（建表、建索引、菜单配置写入）。
3. 确认执行路径：
   - 全新安装：Batch1 -> Batch2 -> Batch3 -> Batch4
   - 增量升级：跳过 Batch1/Batch2 的重复建表部分，优先 Batch3，再 Batch4
4. 若走全量重建，先备份现网数据（特别是 `PUBLIC_NOTICE*` 与 `SYS_MENU_INFO`/`SYS_ROLE_MENU` 相关记录）。
5. 菜单配置执行前确认菜单父节点 `30836` 已存在。

## 快速核查命令
- 表数量预检查：`SELECT COUNT(1) FROM USER_TABLES WHERE TABLE_NAME LIKE 'PUBLIC_NOTICE%';`
- 菜单冲突预检查：`SELECT MENU_ID, COUNT(1) FROM SYS_MENU_INFO WHERE MENU_ID IN (30837,30838) GROUP BY MENU_ID;`
- 角色映射冲突预检查：`SELECT ROLE_ID, MENU_ID, COUNT(1) FROM SYS_ROLE_MENU WHERE MENU_ID IN (30836,30837,30838) GROUP BY ROLE_ID, MENU_ID HAVING COUNT(1)>1;`
