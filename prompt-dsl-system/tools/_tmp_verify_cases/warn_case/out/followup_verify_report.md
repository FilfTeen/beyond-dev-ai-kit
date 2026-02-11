# followup_verify_report

STATUS: **WARN**

- generated_at: 2026-02-10T04:09:33+00:00
- scanner: rg
- mode: full
- tokens_total: 2
- tokens_with_hits: 2
- hits_total: 2
- total_hits_estimate: 2

## Top Tokens
- `prompt-dsl-system/tools/_tmp_verify_cases/warn_case/legacy/path`: hits=1
- `prompt-dsl-system/tools/_tmp_verify_cases/warn_case/legacy/path/OrderSvc.java`: hits=1

## Hit Samples
- `prompt-dsl-system/tools/_tmp_verify_cases/warn_case/README.md:1` token=`prompt-dsl-system/tools/_tmp_verify_cases/warn_case/legacy/path/OrderSvc.java` group=exact_paths :: prompt-dsl-system/tools/_tmp_verify_cases/warn_case/legacy/path/OrderSvc.java
- `prompt-dsl-system/tools/_tmp_verify_cases/warn_case/README.md:1` token=`prompt-dsl-system/tools/_tmp_verify_cases/warn_case/legacy/path` group=old_dirs :: prompt-dsl-system/tools/_tmp_verify_cases/warn_case/legacy/path/OrderSvc.java

## Next
- Run apply-followup-fixes in plan mode and review patch.
- Manually review remaining low-volume hits.
- Re-run verify-followup-fixes after adjustments.
