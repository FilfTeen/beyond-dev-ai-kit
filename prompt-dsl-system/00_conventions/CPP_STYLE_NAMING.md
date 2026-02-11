# C++ 命名/范式规范（博彦泓智公司域专用）

Scope: `prompt-dsl-system/**` 内公司域任务。
技术栈: Java 8 + Spring Boot + LayUI + Oracle/MySQL。

---

## 1. 通用命名原则

| 原则 | 说明 |
|---|---|
| 英文命名 | 所有标识符必须使用英文单词，语义清晰 |
| 短而准确 | 命名应简短但不丢失语义，如 `userId` 优于 `theUserIdentifier` |
| 与字段对齐 | 代码字段名与DB字段名保持可推导对应关系 |
| 禁止拼音 | 禁止使用拼音缩写（如 `yh` 代替 `user`） |
| 禁止虚构缩写 | 禁止自创缩写（如 `hocrecord`），应使用完整单词或业界标准缩写 |
| 禁止混用 | 同一概念在整个模块中只用一个名字（如不得 `record`/`hocrecord` 混用） |

---

## 2. Java 8 + Spring Boot 落地映射

### 2.1 类命名（PascalCase）

| 类型 | 格式 | 示例 |
|---|---|---|
| Entity / PO | `XxxEntity` 或 `XxxPo` | `NoticeEntity`, `OwnerCommitteePo` |
| VO | `XxxVo` | `NoticeDetailVo` |
| DTO | `XxxDto` | `NoticeCreateDto` |
| Service 接口 | `XxxService` | `NoticeService` |
| Service 实现 | `XxxServiceImpl` | `NoticeServiceImpl` |
| Controller | `XxxController` | `NoticeController` |
| Mapper / DAO | `XxxMapper` | `NoticeMapper` |
| 配置类 | `XxxConfig` | `SwaggerConfig` |
| 枚举 | `XxxEnum` 或 `XxxType` | `NoticeStatusEnum` |
| 常量类 | `XxxConstants` | `SystemConstants` |
| 工具类 | `XxxUtil` 或 `XxxUtils` | `DateUtil`, `StringUtils` |

### 2.2 方法命名（lowerCamelCase）

| 场景 | 格式 | 示例 |
|---|---|---|
| 查询单个 | `getXxx` / `findXxx` | `getNoticeById()` |
| 查询列表 | `listXxx` / `findXxxList` | `listNoticeByStatus()` |
| 分页查询 | `pageXxx` | `pageNotice()` |
| 新增 | `addXxx` / `createXxx` | `createNotice()` |
| 更新 | `updateXxx` | `updateNotice()` |
| 删除 | `deleteXxx` / `removeXxx` | `deleteNoticeById()` |
| 判断 | `isXxx` / `hasXxx` | `isPublished()`, `hasPermission()` |
| 转换 | `toXxx` / `convertXxx` | `toVo()`, `convertToDto()` |
| 回调/钩子 | `onXxx` / `handleXxx` | `onStatusChange()` |

### 2.3 常量命名（UPPER_SNAKE_CASE）

```java
// 推荐
public static final int MAX_RETRY_COUNT = 3;
public static final String STATUS_PUBLISHED = "PUBLISHED";

// 禁止：kPrefix 风格在 Java 中不使用
// private static final int kMaxRetry = 3;  // ✗ 不符合 Java 惯例
```

> **决策**：Java 生态惯例为 `UPPER_SNAKE_CASE`，不采用 C++ 的 `kPrefix` 风格。
> 理由：`UPPER_SNAKE_CASE` 在 Spring/MyBatis 生态中广泛使用，优先兼容。

### 2.4 变量命名（lowerCamelCase）

| 类型 | 示例 |
|---|---|
| 局部变量 | `noticeList`, `pageResult`, `currentUser` |
| 成员变量 | `private String noticeTitle;` |
| 参数 | `public void create(NoticeDto noticeDto)` |
| Lambda 参数 | `list.stream().filter(n -> n.getStatus() == 1)` |

### 2.5 包命名（全小写，点分隔）

```
com.indihx.{module}.controller
com.indihx.{module}.service
com.indihx.{module}.service.impl
com.indihx.{module}.mapper
com.indihx.{module}.entity
com.indihx.{module}.vo
com.indihx.{module}.dto
com.indihx.{module}.config
com.indihx.{module}.enums
com.indihx.{module}.util
```

### 2.6 文件/目录命名

| 类型 | 格式 | 示例 |
|---|---|---|
| Java 文件 | PascalCase.java | `NoticeController.java` |
| HTML 模板 | snake_case 或 lowerCamel | `index.html`, `addOrUpdate.html` |
| 配置文件 | kebab-case 或 snake_case | `application-dev.yml` |
| SQL 脚本 | snake_case + 序号 | `V001_create_notice_table.sql` |
| 静态资源 | kebab-case | `notice-detail.js`, `common-utils.js` |

---

## 3. DB 字段命名规则（snake_case）

### 3.1 通用规则

| 规则 | 说明 | 示例 |
|---|---|---|
| snake_case | 全小写，下划线分隔 | `user_name`, `notice_title` |
| 主键后缀 `_id` | 标识字段统一 `_id` 结尾 | `notice_id`, `user_id`, `sect_id` |
| 时间后缀 `_time` | 时间戳字段统一 `_time` 结尾 | `create_time`, `update_time`, `publish_time` |
| 标志后缀 `_flag` | 布尔/标志字段统一 `_flag` 结尾 | `delete_flag`, `read_flag`, `top_flag` |
| 状态字段 `_status` | 状态枚举字段 `_status` 结尾 | `audit_status`, `notice_status` |
| 类型字段 `_type` | 分类类型字段 `_type` 结尾 | `notice_type`, `storage_type` |
| 数量字段 `_count`/`_num` | 计数字段统一后缀 | `read_count`, `seq_num` |

### 3.2 表命名

| 规则 | 示例 |
|---|---|
| 业务表：模块前缀 + snake_case | `PUBLIC_NOTICE`, `PUBLIC_NOTICE_READ` |
| 系统表：`SYS_` 前缀 | `SYS_MENU_INFO`, `SYS_USER_INFO` |
| 关联表：两表名拼接 | `USER_ROLE_REL` |

### 3.3 Java ↔ DB 映射规则

```
DB:   notice_id       → Java: noticeId       (自动驼峰映射)
DB:   create_time     → Java: createTime
DB:   delete_flag     → Java: deleteFlag
DB:   audit_status    → Java: auditStatus
```

MyBatis 配置启用自动驼峰映射：

```yaml
mybatis:
  configuration:
    map-underscore-to-camel-case: true
```

---

## 4. 禁止清单

| 序号 | 禁止行为 | 说明 |
|---|---|---|
| 1 | 拼音缩写 | 如 `gonggao` → 应为 `notice` |
| 2 | 虚构缩写 | 如 `hocrecord` → 应为 `owner_committee_filing` 或语义等价英文 |
| 3 | 名称混用 | 同一概念不得出现 `record` 和 `hocrecord` 两种命名 |
| 4 | 无意义前缀 | 如 `tbl_`、`t_` 前缀在新表中不使用 |
| 5 | 保留字冲突 | 不使用 SQL/Java 保留字作标识符（如 `order`、`status`单独使用时加前缀） |
| 6 | 过长命名 | 单个标识符不超过 40 字符 |
| 7 | 数字开头 | 标识符不得以数字开头 |
