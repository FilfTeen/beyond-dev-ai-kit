-- Batch1_drop_optional.sql
-- context_id: ctx-3a70562661bc
-- trace_id: trace-c4d7acea934f4bbbb5a8979a1de7051b
-- source_files: 01_drop_tables.sql
-- encoding: UTF-8

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

