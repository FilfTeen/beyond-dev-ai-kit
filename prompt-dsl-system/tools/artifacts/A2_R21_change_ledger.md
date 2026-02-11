# A2_R21_change_ledger

## Summary
- Round21 completed with backward-compatible contract extensions and Phase27 regression gate.

## Files Changed
- Modified:
  - `prompt-dsl-system/tools/hongzhi_plugin.py`
  - `prompt-dsl-system/tools/golden_path_regression.sh`
  - `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_plugin_discover.md`
  - `prompt-dsl-system/05_skill_registry/skills.json`
  - `prompt-dsl-system/tools/PLUGIN_RUNNER.md`
  - `prompt-dsl-system/00_conventions/FACT_BASELINE.md`
  - `prompt-dsl-system/00_conventions/COMPLIANCE_MATRIX.md`
- Added:
  - `prompt-dsl-system/tools/layout_adapters.py`
  - `prompt-dsl-system/05_skill_registry/skills/governance/skill_governance_plugin_discover_with_hints.yaml`
  - `prompt-dsl-system/tools/_tmp_structure_cases/case6_maven_multi_module/pom.xml`
  - `prompt-dsl-system/tools/_tmp_structure_cases/case6_maven_multi_module/notice-core/src/main/java/com/example/notice/controller/NoticeController.java`
  - `prompt-dsl-system/tools/_tmp_structure_cases/case6_maven_multi_module/billing-core/src/main/java/com/example/billing/controller/BillingController.java`
  - `prompt-dsl-system/tools/_tmp_structure_cases/case7_nonstandard_java_root/backend/src/main/java/com/example/nonstd/controller/AssetController.java`
  - `prompt-dsl-system/tools/_tmp_structure_cases/case7_nonstandard_java_root/backend/src/main/resources/templates/asset/index.html`

## Validation Evidence
- `./prompt-dsl-system/tools/run.sh validate --repo-root .`
  - Errors=0, Warnings=0
- `HONGZHI_VALIDATE_STRICT=1 ./prompt-dsl-system/tools/run.sh validate --repo-root .`
  - Errors=0, Warnings=0
- `bash prompt-dsl-system/tools/golden_path_regression.sh --repo-root .`
  - **64 / 64 PASS**
  - Includes new Phase27 checks:
    - hint_loop_strict_fail_then_apply_pass
    - adapter_maven_multi_module_smoke
    - adapter_nonstandard_java_root_smoke
    - reuse_validated_smoke
    - governance_disabled_zero_write
    - capability_index_records_hint_runs

## Behavior Deltas
- Discover can emit and consume hint bundles without touching target repo.
- Adapter-backed layout/root inference now visible in `layout_details`.
- Smart reuse now has explicit validation marker (`reuse_validated`).
