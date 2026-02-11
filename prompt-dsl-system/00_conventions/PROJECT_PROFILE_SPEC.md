# Project Profile Spec

## 用途

为 `pipeline_project_bootstrap` 提供项目级输入元数据，使装配线能够准确理解项目边界和能力需求。

## 文件位置

```text
prompt-dsl-system/projects/<project_key>/profile.yaml
```

## 必填字段

```yaml
project_key: "<unique_project_identifier>"
project_name: "<human_readable_name>"
description: "<one_line_description>"
modules:
  - name: "<module_name>"
    path: "<repository_relative_path>"
    capabilities:
      - "<capability_description>"
target_domain: "<skill_domain>"    # e.g. "property", "notice", "committee"
constraints:
  - "<project_level_constraint>"
```

## 可选字段

```yaml
db_targets: ["oracle", "dm8", "mysql"]
frontend_framework: "layui"
process_engine: "activiti"
existing_skills: []    # list of skill names that already cover some capabilities
```

## 使用规则

1. `pipeline_project_bootstrap` Step1 **应**尝试读取 `projects/<project_key>/profile.yaml`。
2. 若文件存在 → 用作 Step1 的能力映射输入。
3. 若文件不存在 → Step1 **必须**输出 `required_additional_information` checklist，禁止猜测项目结构。
4. Profile 不可在 pipeline 运行过程中被修改（只读输入）。

## 向后兼容

- Profile 为可选文件。不存在时 pipeline 仍可运行（降级为手动输入模式）。
- 没有 profile 时，所有项目信息必须通过 `project_scope` 和 `target_capabilities` 参数提供。
