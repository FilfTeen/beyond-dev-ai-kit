# Golden Path Regression Report

Generated: 2026-02-11T13:55:15Z
Repo Root: /Users/dwight/Downloads/【洪智科技】本地存档/beyond-dev-ai-kit

## Results

| # | Check | Result |
| --- | --- | --- |

| 1 | Phase1:audit | PASS |
| 2 | Phase1:lint | PASS |
| 3 | Phase2:template_exists | PASS |
| 4 | Phase2:registry_update | PASS |
| 5 | Phase3:audit(+staging) | PASS |
| 6 | Phase3:lint(+staging) | PASS |
| 7 | Phase4:promote | PASS |
| 8 | Phase5:audit(deployed) | PASS |
| 9 | Phase6:migration_pipeline_exists | PASS |
| 10 | Phase6:migration_lint | PASS |
| 11 | Phase7:profile_template_exists | PASS |
| 12 | Phase7:scanner_syntax | PASS |
| 13 | Phase9:roots_discover_syntax | PASS |
| 14 | Phase9:scanner_multi_root_support | PASS |
| 15 | Phase10:structure_discover_syntax | PASS |
| 16 | Phase10:structure_discover_concurrent | PASS |
| 17 | Phase11:cross_project_diff_syntax | PASS |
| 18 | Phase12:auto_module_discover_syntax | PASS |
| 19 | Phase12:auto_discover_finds_module | PASS |
| 20 | Phase13:endpoint_v2_extracts_method | PASS |
| 21 | Phase14:cache_reports_stats | PASS |
| 22 | Phase14:cache_hit_in_output | PASS |
| 23 | Phase15:plugin_syntax | PASS |
| 24 | Phase15:plugin_discover_output | PASS |
| 25 | Phase16:plugin_read_only_contract | PASS |
| 26 | Phase17:plugin_cache_warm | PASS |
| 27 | Phase18:plugin_governance_disabled | PASS |
| 28 | Phase19:plugin_module_entrypoint | PASS |
| 29 | Phase19:governance_allowlist_block | PASS |
| 30 | Phase19:governance_deny_block | PASS |
| 31 | Phase19:permit_token_override | PASS |
| 32 | Phase20:capability_index_created | PASS |
| 33 | Phase20:latest_pointer_created | PASS |
| 34 | Phase21:smart_reused_summary | PASS |
| 35 | Phase21:smart_reuse_effective | PASS |
| 36 | Phase22:governance_no_state_write | PASS |
| 37 | Phase23:uninstalled_install_hint | PASS |
| 38 | Phase23:package_import_smoke | PASS |
| 39 | Phase23:console_entry_smoke | PASS |
| 40 | Phase23:governance_disabled_no_outputs | PASS |
| 41 | Phase23:capabilities_stdout_contract | PASS |
| 42 | Phase24:sdist_build_smoke | PASS |
| 43 | Phase24:wheel_install_smoke | PASS |
| 44 | Phase24:gitignore_guard | PASS |
| 45 | Phase24:version_triple_present | PASS |
| 46 | Phase24:gov_block_has_versions_and_zero_write | PASS |
| 47 | Phase25:token_ttl_expired_block | PASS |
| 48 | Phase25:token_scope_block | PASS |
| 49 | Phase25:symlink_bypass_denied | PASS |
| 50 | Phase25:limits_hit_normal_warn | PASS |
| 51 | Phase25:limits_hit_strict_fail | PASS |
| 52 | Phase25:capability_index_gated_by_governance | PASS |
| 53 | Phase25:pipeline_status_decide_discover_smoke | PASS |
| 54 | Phase26:calibration_low_confidence_exit21_strict | PASS |
| 55 | Phase26:calibration_non_strict_warn_exit0 | PASS |
| 56 | Phase26:calibration_outputs_exist_in_workspace | PASS |
| 57 | Phase26:capabilities_contains_calibration_fields | PASS |
| 58 | Phase27:hint_loop_strict_fail_then_apply_pass | PASS |
| 59 | Phase27:adapter_maven_multi_module_smoke | PASS |
| 60 | Phase27:adapter_nonstandard_java_root_smoke | PASS |
| 61 | Phase27:reuse_validated_smoke | PASS |
| 62 | Phase27:governance_disabled_zero_write | PASS |
| 63 | Phase27:capability_index_records_hint_runs | PASS |
| 64 | Phase28:strict_exit21_hints_bundle_schema | PASS |
| 65 | Phase28:apply_hints_verified_pass | PASS |
| 66 | Phase28:expired_bundle_strict_exit22 | PASS |
| 67 | Phase28:governance_disabled_zero_write | PASS |
| 68 | Phase28:token_scope_missing_hint_bundle_block | PASS |
| 69 | Phase28:capability_index_gated_when_governance_denied | PASS |
| 70 | Phase29:federated_index_smoke | PASS |
| 71 | Phase29:index_list_smoke | PASS |
| 72 | Phase29:index_query_strict_filters_limits_hit | PASS |
| 73 | Phase29:index_query_include_limits_hit | PASS |
| 74 | Phase29:index_explain_smoke | PASS |
| 75 | Phase29:token_scope_missing_federated_index_strict_exit24 | PASS |
| 76 | Phase29:token_scope_missing_federated_index_non_strict_warn | PASS |
| 77 | Phase29:governance_disabled_zero_write_federated | PASS |
| 78 | Phase30:status_index_zero_touch | PASS |
| 79 | Phase30:read_only_guard_not_truncated_by_max_files | PASS |
| 80 | Phase30:policy_parse_fail_closed | PASS |
| 81 | Phase30:machine_line_path_with_spaces_safe | PASS |
| 82 | Phase30:jsonl_append_concurrency_no_loss | PASS |
| 83 | Phase30:discover_io_reduction_same_output | PASS |
| 84 | Phase30:endpoint_composed_annotation_extracts | PASS |
| 85 | Phase30:hint_apply_effectiveness_signal | PASS |
| 86 | Phase31:scan_graph_syntax_smoke | PASS |
| 87 | Phase31:discover_uses_scan_graph | PASS |
| 88 | Phase31:scan_graph_cache_warm_hit | PASS |
| 89 | Phase31:discover_io_reduction_delta | PASS |
| 90 | Phase31:profile_reuses_scan_graph | PASS |
| 91 | Phase31:diff_reuses_scan_graph | PASS |
| 92 | Phase31:governance_disabled_zero_write_still | PASS |
| 93 | Phase31:strict_mismatch_exit25 | PASS |
| 94 | Phase32:scan_graph_schema_version_present | PASS |
| 95 | Phase32:scan_graph_strict_mismatch_reason_emitted | PASS |
| 96 | Phase32:discover_profile_diff_reuse_no_rescan | PASS |
| 97 | Phase32:machine_line_json_payload_additive | PASS |
| 98 | Phase32:governance_disabled_zero_write_still | PASS |
| 99 | Phase32:read_only_guard_full_snapshot_ignores_limits | PASS |
| 100 | Phase33:machine_json_roundtrip_parse | PASS |
| 101 | Phase33:machine_json_no_newlines | PASS |
| 102 | Phase33:deterministic_artifacts_order | PASS |
| 103 | Phase33:deterministic_modules_order | PASS |
| 104 | Phase33:mismatch_reason_enum_and_suggestion | PASS |
| 105 | Phase33:status_index_never_probe_writable | PASS |
| 106 | Phase34:contract_schema_exists_and_valid_json | PASS |
| 107 | Phase34:contract_validator_smoke | PASS |
| 108 | Phase34:contract_validator_on_discover_stdout | PASS |
| 109 | Phase34:contract_validator_on_gov_block_stdout | PASS |
| 110 | Phase34:contract_validator_on_exit25_mismatch_stdout | PASS |
| 111 | Phase34:contract_schema_additive_guard | PASS |
| 112 | Phase35:governance_skills_deployed | PASS |
| 113 | Phase35:machine_lines_include_company_scope | PASS |
| 114 | Phase35:company_scope_gate_default_off | PASS |
| 115 | Phase35:company_scope_mismatch_block_exit26 | PASS |
| 116 | Phase35:company_scope_mismatch_zero_write | PASS |
| 117 | Phase35:company_scope_match_required_allows | PASS |
| 118 | Phase8:guard_strict_no_vcs_fails | PASS |

## Summary

**118 / 118** checks passed.

**OVERALL: PASS**
