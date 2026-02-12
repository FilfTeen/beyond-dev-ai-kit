# Project Stack Knowledge Base

This directory stores per-project technical stack profiles.

- Declared profile: `project_stacks/<project_key>/stack_profile.yaml`
- Scanner profile: `project_stacks/<project_key>/stack_profile.discovered.yaml`
- Template: `project_stacks/template/stack_profile.yaml`

Scanner example:

```bash
/usr/bin/python3 prompt-dsl-system/tools/project_stack_scanner.py \
  --repo-root /abs/path/to/target-project \
  --project-key xywygl \
  --kit-root /abs/path/to/beyond-dev-ai-kit
```
