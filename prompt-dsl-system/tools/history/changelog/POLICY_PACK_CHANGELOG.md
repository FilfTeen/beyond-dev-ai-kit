# POLICY_PACK Changelog

## Summary
Implemented a unified policy pack for tools with merge priority:
- `CLI (--policy-override key=value)`
- repo override (`.prompt-dsl-policy.yaml` / `.prompt-dsl-policy.json`)
- tools default (`prompt-dsl-system/tools/policy.yaml`)
- hardcoded fallbacks

## Added
- `prompt-dsl-system/tools/policy.yaml`
- `prompt-dsl-system/tools/policy_loader.py`
- `prompt-dsl-system/tools/POLICY_PACK_TEST_NOTES.md`

## Modified
- `prompt-dsl-system/tools/pipeline_runner.py`
  - Added global `--policy` and repeatable `--policy-override`.
  - Validate now refreshes:
    - `policy_effective.json`
    - `policy_sources.json`
    - `policy.json`
  - Validate now performs policy parse-check reporting (`report.policy.errors`) and counts parse failures as validate errors.
  - Added policy summary in validate output.
  - Wired policy defaults into command handlers and subprocess forwarding (loop/risk/snapshot/trace/snapshot index/prune/open).
- `prompt-dsl-system/tools/run.sh`
  - Added wrapper-level `--policy` and `--policy-override` parsing.
  - Automatically injects `--policy prompt-dsl-system/tools/policy.yaml` when file exists and user did not specify one.
  - Ensures policy args are passed as global args before subcommand.
- `prompt-dsl-system/tools/health_reporter.py`
- `prompt-dsl-system/tools/health_runbook_generator.py`
- `prompt-dsl-system/tools/loop_detector.py`
- `prompt-dsl-system/tools/risk_gate.py`
- `prompt-dsl-system/tools/snapshot_manager.py`
- `prompt-dsl-system/tools/snapshot_prune.py`
- `prompt-dsl-system/tools/snapshot_indexer.py`
- `prompt-dsl-system/tools/snapshot_open.py`
- `prompt-dsl-system/tools/trace_indexer.py`
- `prompt-dsl-system/tools/trace_open.py`
- `prompt-dsl-system/tools/trace_diff.py`
- `prompt-dsl-system/tools/trace_bisect_helper.py`
- `prompt-dsl-system/tools/README.md`

## Compatibility
- Existing commands remain valid.
- If policy files are missing/unparseable, tools fall back to existing hardcoded defaults.
- CLI args still have highest priority.

## Rollback
Fast rollback options:
1. Remove policy pack files:
   - `prompt-dsl-system/tools/policy.yaml`
   - `prompt-dsl-system/tools/policy_loader.py`
2. Revert modified tools scripts to previous versions.
3. Keep running existing commands without policy flags (hardcoded defaults still work).
