# R19 Scan Notes

Date: 2026-02-11
Repo: /Users/dwight/Downloads/【洪智科技】本地存档/beyond-dev-ai-kit

## Located Package/CLI Chain
- Package entry: `prompt-dsl-system/tools/hongzhi_ai_kit/__main__.py`
- CLI wrapper: `prompt-dsl-system/tools/hongzhi_ai_kit/cli.py`
- Runtime core: `prompt-dsl-system/tools/hongzhi_plugin.py`

## Located State/Capability Files
- Capability store: `prompt-dsl-system/tools/hongzhi_ai_kit/capability_store.py`
- Path strategy: `prompt-dsl-system/tools/hongzhi_ai_kit/paths.py`
- Current capability registry update path:
  - `capability_index.json`
  - `<fp>/latest.json`
  - `<fp>/runs/<run_id>/run_meta.json`

## Located Machine-Readable Contract Outputs
- `HONGZHI_CAPS ...` in `hongzhi_plugin.py`
- `HONGZHI_STATUS ...` in `hongzhi_plugin.py`
- `HONGZHI_GOV_BLOCK ...` in `hongzhi_plugin.py`
- Summary line: `hongzhi_ai_kit_summary ...`

## Governance & Token Current State (before R19)
- `check_root_governance()` currently treats any non-empty token as unconditional bypass.
- No TTL/scope validation yet.
- Allow/deny matching uses string prefix logic, not explicit realpath-within helper.

## Limits Current State (before R19)
- CLI has `--max-files` / `--max-seconds`, but limits behavior/exit code contract is not fully enforced.
- No dedicated exit code 20 path.
- Summary line lacks `limits_hit` machine key.

## Skills/Pipeline Current State (before R19)
- Skills:
  - `skill_governance_plugin_runner.yaml`
  - `skill_governance_plugin_discover.yaml`
- No dedicated `skill_governance_plugin_status.yaml` yet.
- `pipeline_plugin_discover.md` currently uses Step0/Step1/Step2 flow, not explicit status->decide->discover machine decision gate.

## Regression Current State (before R19)
- Existing phases up to Phase24.
- No Phase25 token TTL/scope/symlink/limits/pipeline chain checks yet.
