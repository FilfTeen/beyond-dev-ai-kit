# A1_R19_impact_tree

## Goal
Round19: strengthen hongzhi-ai-kit as agent-native, governed, machine-readable, and scalable read-only scanner.

## Impact Tree
- Governance Core
  - `prompt-dsl-system/tools/hongzhi_plugin.py`
    - permit-token TTL/scope validation
    - realpath/symlink hardening for allow/deny
    - governance metadata enrichment (`policy_hash`, token reason/scope)
- Contract Surface
  - `hongzhi_ai_kit_summary` adds `limits_hit/limits_reason`
  - `capabilities.json` adds explicit planning keys:
    - `layout`, `module_candidates`, `ambiguity_ratio`
    - `limits_hit`, `limits`, `scan_stats`
  - `capabilities.jsonl` appends same planning keys
- Capability Registry
  - capability_index entry schema v1 fields:
    - `repo_fingerprint`, `latest`, `runs[]`, `created_at`
    - `versions{package,plugin,contract}`
    - `governance{enabled,token_used,policy_hash}`
- Performance Limits
  - `--max-files/--max-seconds` machine-visible and strict fail (`exit=20`)
- Prompt-DSL Integration
  - new skill: `skill_governance_plugin_status`
  - pipeline upgraded to `status -> decide -> discover` hard gate
- Regression
  - `golden_path_regression.sh` Phase25 adds governance/token/limits/pipeline chain checks

## Risk Notes
- Governance behavior changed from plain token bypass to token validation when JSON token metadata is used.
- Limits strict mode introduces new non-zero code path (`20`) by design.
