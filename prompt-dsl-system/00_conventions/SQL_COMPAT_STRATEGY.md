# SQL 双栈交付规范（博彦泓智公司域专用）

Scope: `prompt-dsl-system/**` 内公司域任务。
绑定: `HONGZHI_COMPANY_CONSTITUTION.md` Rule 10 (SQL Portability First) 和 Rule 11 (Dual SQL When Needed)。

---

## 1. 通用SQL优先原则

### 1.1 默认策略

所有 SQL 交付物**必须首先**尝试使用 ANSI SQL 标准语法。

| 特性 | ANSI 通用写法 | 说明 |
|---|---|---|
| 字符串连接 | `CONCAT(a, b)` 或 `a || b` | 避免 `+` |
| 空值处理 | `COALESCE(x, default)` | 避免 `NVL` / `IFNULL` |
| 分页 | `OFFSET ... FETCH NEXT ... ROWS ONLY` | SQL:2008 标准 |
| 日期格式化 | 业务层处理 | 数据库只存 `DATE`/`TIMESTAMP` |
| 序列/自增 | 业务层生成或使用 `IDENTITY`(ANSI SQL:2003) | 避免 `SEQUENCE` 依赖 |
| 字符串截取 | `SUBSTRING(str FROM pos FOR len)` | 避免 `SUBSTR` |
| 条件表达式 | `CASE WHEN ... THEN ... ELSE ... END` | 避免 `DECODE` |
| 类型转换 | `CAST(x AS type)` | 避免 `TO_NUMBER` / `TO_CHAR` |

### 1.2 通用性判定流程

```
需求 SQL
  ├── 能用 ANSI 标准？ → YES → 产出单一 portable.sql
  └── 不能？→ 必须产出 oracle.sql + mysql.sql 双版本
```

---

## 2. 双版本交付规范

### 2.1 触发条件

当遇到以下**不可通用**的功能时，必须产出 Oracle + MySQL 双套：

| 特性 | Oracle 写法 | MySQL 写法 |
|---|---|---|
| 分页 | `ROWNUM` / `ROW_NUMBER() OVER()` | `LIMIT offset, count` |
| 序列 | `seq_name.NEXTVAL` | `AUTO_INCREMENT` |
| 系统日期 | `SYSDATE` | `NOW()` / `CURRENT_TIMESTAMP` |
| 空字符串 | 等同 `NULL` | 空字符串 ≠ `NULL` |
| 递归查询 | `CONNECT BY` / `WITH RECURSIVE` | `WITH RECURSIVE` |
| MERGE | `MERGE INTO` | `INSERT ... ON DUPLICATE KEY UPDATE` |
| 批量插入 | `INSERT ALL INTO ... SELECT FROM DUAL` | `INSERT INTO ... VALUES (...), (...)` |
| 数据类型 | `NUMBER(p,s)`, `VARCHAR2`, `CLOB` | `INT`, `VARCHAR`, `TEXT` |

### 2.2 目录结构模板

```
sql/
├── portable/                    # 通用SQL（能通过 ANSI 标准的）
│   ├── V001_create_tables.sql
│   └── V002_create_indexes.sql
├── oracle/                      # Oracle 专用
│   ├── V001_create_sequences.sql
│   ├── V003_oracle_specific.sql
│   └── README_oracle.md
├── mysql/                       # MySQL 专用
│   ├── V001_auto_increment.sql
│   ├── V003_mysql_specific.sql
│   └── README_mysql.md
└── README.md                    # 执行顺序说明
```

### 2.3 文件命名规则

- 版本前缀：`V{NNN}_`（三位数字，如 `V001_`）
- 通用脚本：放 `portable/`，Oracle/MySQL 均执行
- 专用脚本：放对应方言目录，文件名需对应（如 Oracle 的 `V003` 对应 MySQL 的 `V003`）

### 2.4 执行顺序文档

每个 `README.md` 必须包含：

```markdown
## 执行顺序
1. portable/V001_create_tables.sql     -- 通用建表
2. portable/V002_create_indexes.sql    -- 通用索引
3. oracle/V001_create_sequences.sql    -- Oracle序列（仅Oracle执行）
   或 mysql/V001_auto_increment.sql    -- MySQL自增（仅MySQL执行）
```

---

## 3. 业务代码方言适配策略

### 3.1 禁止硬编码方言

```java
// ✗ 禁止：在代码里硬编码SQL方言
String sql = "SELECT ROWNUM ...";  // Oracle专用
String sql = "SELECT ... LIMIT 10"; // MySQL专用

// ✓ 正确：通过配置切换
@Value("${app.db.dialect:oracle}")
private String dbDialect;
```

### 3.2 推荐适配方案（按优先级排列）

#### 方案A：MyBatis `<if>` + 方言参数（推荐，兼容优先）

```xml
<select id="pageNotice" resultType="NoticeVo">
  SELECT * FROM (
    <if test="_databaseId == 'oracle'">
      SELECT t.*, ROWNUM rn FROM (
    </if>
    SELECT notice_id, notice_title, create_time
    FROM PUBLIC_NOTICE
    WHERE delete_flag = 0
    ORDER BY create_time DESC
    <if test="_databaseId == 'oracle'">
      ) t WHERE ROWNUM &lt;= #{endRow}
      ) WHERE rn &gt; #{startRow}
    </if>
    <if test="_databaseId == 'mysql'">
      LIMIT #{offset}, #{pageSize}
    </if>
  )
</select>
```

配置 `mybatis.configuration.database-id`:

```yaml
# application.yml
mybatis:
  configuration:
    database-id: oracle   # 或 mysql
```

#### 方案B：SqlProvider 动态路由（自洽方案）

```java
public class NoticeSqlProvider {
    
    @SelectProvider(type = NoticeSqlProvider.class, method = "pageNotice")
    List<NoticeVo> pageNotice(@Param("dialect") String dialect, 
                               @Param("offset") int offset, 
                               @Param("pageSize") int pageSize);
    
    public static String pageNotice(String dialect, int offset, int pageSize) {
        if ("mysql".equals(dialect)) {
            return "SELECT ... LIMIT " + offset + ", " + pageSize;
        }
        // default: oracle
        return "SELECT ... ROWNUM ...";
    }
}
```

#### 方案C：多Mapper文件（最小侵入，仅限差异极大时）

```
mapper/
├── NoticeMapper.java          # 接口
├── NoticeMapper.xml           # 通用SQL
├── NoticeMapper-oracle.xml    # Oracle差异覆盖
└── NoticeMapper-mysql.xml     # MySQL差异覆盖
```

Spring Boot 配置按方言加载：

```yaml
mybatis:
  mapper-locations:
    - classpath:mapper/*Mapper.xml
    - classpath:mapper/*Mapper-${app.db.dialect}.xml
```

### 3.3 方案选择决策树

```
SQL方言差异
  ├── 仅分页差异 → 方案A（MyBatis <if> 最简）
  ├── 多处差异但结构相似 → 方案B（SqlProvider 集中管理）
  └── SQL完全不同（如存储过程） → 方案C（多Mapper文件隔离）
```

---

## 4. 与现有系统的关系

- 本规范细化了 `HONGZHI_COMPANY_CONSTITUTION.md` Rule 10/11 的执行标准
- `skill_hongzhi_universal_ops.yaml` 中 `sql_policy.prefer_portable_sql` 和 `sql_policy.dual_sql_when_needed` 是本规范的运行时参数化表达
- 所有 SQL 类 pipeline（如 `pipeline_sql_oracle_to_dm8.md`）的产出物应遵守本规范的目录结构
