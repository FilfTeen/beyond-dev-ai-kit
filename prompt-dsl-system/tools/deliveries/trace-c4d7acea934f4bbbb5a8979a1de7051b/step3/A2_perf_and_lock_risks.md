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
