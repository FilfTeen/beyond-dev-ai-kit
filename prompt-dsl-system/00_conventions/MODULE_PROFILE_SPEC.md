# Module Profile Spec — Three-Layer Model

## 概述

Module Profile 采用三层合并模型，为 `pipeline_module_migration` 提供稳定输入：

| Layer | 名称 | 稳定性 | 位置 | 可删除 |
| --- | --- | --- | --- | --- |
| 0 | Project Defaults | 高 | `projects/<project_key>/profile.yaml` | 否 |
| 1 | Module Declared | 高 | `module_profiles/<project_key>/<module_key>.yaml` | 否 |
| 2 | Module Discovered | 低 | `module_profiles/<project_key>/<module_key>.discovered.yaml` | 是 |
| 2R | Module Roots Discovered | 低 | `module_profiles/<project_key>/<module_key>.roots.discovered.yaml` | 是 |
| 2S | Structure Discovered | 低 | `module_profiles/<project_key>/<module_key>.structure.discovered.yaml` | 是 |

## 合并规则

```text
Effective Profile = merge(Layer0, Layer1, Layer2, Layer2R)
优先级: Layer0 < Layer1 < Layer2 (仅限 discovery.* 字段)
```

> [!IMPORTANT]
> Layer2 (discovered) **仅能覆盖** `discovery.*` 与 `integration_points.discovered_*` 字段。
> 以下字段 **不可被 discovered 覆盖**：`scope.forbidden_paths`、`migration_objectives`、`identity.*`。
> `allowed_module_roots` 由 Layer2R 自动生成，Layer1 只提供 identity hints 作为发现约束。

### Multi-Root 概念

模块通常跨多个目录（backend Java、web templates、SQL scripts、MiniApp pages）。
**Layer1 不硬编码路径**，只提供 identity hints：

```text
identity.backend_package_hint → e.g. "com.indihx.notice"
identity.web_path_hint        → e.g. "backstage/notice"
identity.keywords             → optional additional search terms
```

`module_roots_discover.py` 读取 hints，扫描 repo 结构，生成 `roots.discovered.yaml`：

```text
effective.allowed_module_roots = Layer2R.roots (auto-discovered)
```

## Profile Kinds

### declared（Layer1）— 模块本质，抗变化

只含模块边界、目标、集成点类型、方言集合、风险预算、identity hints、discovery hints。
**禁止包含**：具体类名、具体路由、表名、字段名、具体文件路径（这些属于 discovered）。

### discovered（Layer2）— 扫描索引，可再生

由 `module_profile_scanner.py` 自动生成。只含文件清单、grep 命中、NavIndex、置信度、fingerprint。
**不得包含**：硬业务承诺、边界定义、迁移目标。

### roots.discovered（Layer2R）— 根路径索引，可再生

由 `module_roots_discover.py` 自动生成。只含发现的模块根路径及每个根的 fingerprint。
**不得包含**：业务逻辑、迁移目标。

## 文件位置约定

```text
Layer0:  prompt-dsl-system/projects/<project_key>/profile.yaml
Layer1:  prompt-dsl-system/module_profiles/<project_key>/<module_key>.yaml
Layer2:  prompt-dsl-system/module_profiles/<project_key>/<module_key>.discovered.yaml
Layer2R: prompt-dsl-system/module_profiles/<project_key>/<module_key>.roots.discovered.yaml
```

## Declared Profile Schema（Layer1 必填字段）

```yaml
profile_kind: "declared"                    # 固定值
profile_version: "1.1"

identity:
  project_key: "<project_identifier>"       # e.g. xywygl
  module_key: "<module_identifier>"         # e.g. notice
  module_name: "<human_readable_name>"      # e.g. 公告模块
  profile_id: "<project_key>/<module_key>"  # 唯一标识
  backend_package_hint: "<java_package>"    # e.g. com.indihx.notice — 用于 roots 自动发现
  web_path_hint: "<web_template_path>"      # e.g. backstage/notice — 用于 roots 自动发现
  keywords: []                              # optional: additional module identification terms

scope:
  allowed_module_root: "<repo_relative_path>"   # skill/pipeline 生成目录
  forbidden_paths:
    - "/sys"
    - "/error"
    - "/util"
    - "/vote"

db:
  source_dialect: "oracle"
  dialects: ["oracle", "mysql", "dm8"]

integration_points:
  declared:
    - "controller"
    - "service"
    - "mapper"
    - "sql_script"

migration_objectives:
  goals:
    - "sql_portability"
  risk_budget: "low"                        # low/medium/high

discovery_hints:
  grep_patterns: ["Notice", "notice"]
  include_globs: ["**/*.java", "**/*.xml", "**/*.html", "**/*.sql"]
  exclude_globs: ["**/node_modules/**", "**/target/**"]
```

## integration_points 枚举（固定）

| 值 | 说明 |
| --- | --- |
| `controller` | REST Controller 层 |
| `service` | Service 业务层 |
| `repository` | Spring Data Repository |
| `mapper` | MyBatis Mapper (XML + interface) |
| `sql_script` | DDL/DML 脚本 |
| `ui_pages` | 前端页面 (HTML/Vue) |
| `workflow_activiti` | Activiti 流程定义 |
| `api_routes` | API 路由配置 |
| `dto` | Data Transfer Object |
| `vo` | View Object |
| `config` | 配置文件 |

## Roots Discovered Schema（Layer2R 自动生成）

```yaml
profile_kind: "roots_discovered"
profile_version: "1.0"

identity:
  project_key: "<same>"
  module_key: "<same>"
  profile_id: "<same>"

roots:
  generated_at: "<ISO-8601>"
  scanner_version: "1.0"
  entries:
    - path: "<repo_relative_path>"
      category: "backend_java"              # backend_java|web_template|sql|miniapp|static|other
      fingerprint:
        file_count: 0
        total_bytes: 0
        latest_mtime: "<ISO-8601>"
```

## Discovered Profile Schema（Layer2 自动生成）

```yaml
profile_kind: "discovered"
profile_version: "1.0"

identity:
  project_key: "<same>"
  module_key: "<same>"
  profile_id: "<same>"

discovery:
  generated_at: "<ISO-8601>"
  scanner_version: "1.0"
  confidence: "high"

  fingerprint:
    file_count: 0
    total_bytes: 0
    latest_mtime: "<ISO-8601>"

  file_index:
    controller: []
    service: []
    mapper: []
    sql_script: []
    ui_pages: []
    workflow_activiti: []
    config: []
    other: []

  navindex:
    - pattern: "Notice"
      hits:
        - file: "<path>"
          line: 42
          snippet: "public class NoticeController"

integration_points:
  discovered_controller: []
  discovered_service: []
  discovered_mapper: []
```

## required_additional_information 条件

以下任一缺失时，pipeline **必须停止**并输出 checklist（禁止猜测）：

1. `identity.backend_package_hint` 和 `identity.web_path_hint` 均缺失
2. `db.dialects` 缺失
3. `migration_objectives.goals` 缺失

## 向后兼容

- Layer0 (project profile) 遵循 `PROJECT_PROFILE_SPEC.md`，可选。
- Layer1 (declared) 必须存在才能运行 `pipeline_module_migration`。
- Layer2 (discovered) 完全可选，可随时重新生成或删除。
- Layer2R (roots.discovered) 完全可选，可随时重新生成或删除。
- `scope.allowed_module_root` 仍保留用于 skill/pipeline 生成目录约束。
