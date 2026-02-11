# A1_R21_impact_tree

## Scope
- Round21 implemented in `prompt-dsl-system/**` only.
- Target project `repo_root` write protections unchanged (snapshot-diff guard + governance gate).

## Change Tree
- Plugin runtime (`prompt-dsl-system/tools/hongzhi_plugin.py`)
  - Hint Loop
    - Added `--apply-hints <path>` and `--hint-strategy {conservative|aggressive}`.
    - Strict `needs_human_hint` path now emits discover hint bundle (`discover/hints.json`).
    - Summary fields extended: `hint_bundle`, `hint_applied`.
    - New stdout pointer line when emitted: `HONGZHI_HINTS <abs_path> ...`.
    - Capabilities fields extended (backward-compatible): `hints{...}`.
  - Layout Adapters v1 integration
    - Adapter pass before/after candidate ranking for root/layout inference.
    - Capabilities fields extended with `layout_details`.
  - Smart incremental consistency
    - Added machine field `reuse_validated` in summary/capabilities/jsonl.
  - Limits ergonomics
    - Added `limits_suggestion` consistently across discover/diff/profile/migrate.
- New helper module
  - `prompt-dsl-system/tools/layout_adapters.py`
    - Detects maven multi-module / non-standard java roots.
    - Emits roots entries with `backend_java` / `web_template` kinds.
- Prompt-DSL orchestration
  - New skill: `skill_governance_plugin_discover_with_hints.yaml`.
  - Updated pipeline: `pipeline_plugin_discover.md` to include hint-loop decision semantics (`enable_hint_loop`).
  - Updated registry: `prompt-dsl-system/05_skill_registry/skills.json`.
- Regression gate
  - `golden_path_regression.sh` added Phase27 (6 checks).
  - Added fixtures:
    - `case6_maven_multi_module`
    - `case7_nonstandard_java_root`

## Risk Surface
- Contract compatibility risk: mitigated by additive-only fields and preserving existing lines (`HONGZHI_CAPS`, summary).
- Governance bypass risk: unchanged; blocked paths (`10/11/12`) still return before any workspace/state writes.
- Discover scoring drift risk: contained via optional hint strategy and explicit machine flags.
