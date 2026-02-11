-- Batch_all_merged.sql
-- context_id: ctx-3a70562661bc
-- trace_id: trace-c4d7acea934f4bbbb5a8979a1de7051b
-- source_files: 01_drop_tables.sql,02_create_public_notice.sql,03_create_public_notice_scope.sql,04_create_public_notice_cover.sql,05_create_public_notice_external_source.sql,07_create_public_notice_read.sql,06_create_index.sql,08_upgrade_from_legacy.sql,10_menu_and_role_config.sql
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
