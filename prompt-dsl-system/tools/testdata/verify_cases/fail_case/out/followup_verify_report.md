# followup_verify_report

STATUS: **FAIL**

- generated_at: 2026-02-10T04:09:34+00:00
- scanner: rg
- mode: full
- tokens_total: 2
- tokens_with_hits: 2
- hits_total: 2
- total_hits_estimate: 2

## Top Tokens
- `prompt-dsl-system/tools/_tmp_verify_cases/fail_case/legacy/path`: hits=1
- `prompt-dsl-system/tools/_tmp_verify_cases/fail_case/legacy/path/PriceSvc.java`: hits=1

## Hit Samples
- `prompt-dsl-system/tools/_tmp_verify_cases/fail_case/src/main/java/com/acme/Test.java:3` token=`prompt-dsl-system/tools/_tmp_verify_cases/fail_case/legacy/path/PriceSvc.java` group=exact_paths :: String ref = "prompt-dsl-system/tools/_tmp_verify_cases/fail_case/legacy/path/PriceSvc.java";
- `prompt-dsl-system/tools/_tmp_verify_cases/fail_case/src/main/java/com/acme/Test.java:3` token=`prompt-dsl-system/tools/_tmp_verify_cases/fail_case/legacy/path` group=old_dirs :: String ref = "prompt-dsl-system/tools/_tmp_verify_cases/fail_case/legacy/path/PriceSvc.java";

## Next
- Run apply-followup-fixes in plan mode, then apply with ACK if needed.
- Prioritize manual cleanup in src/main/java or pages paths.
- Re-run debug-guard and verify-followup-fixes before next run.
