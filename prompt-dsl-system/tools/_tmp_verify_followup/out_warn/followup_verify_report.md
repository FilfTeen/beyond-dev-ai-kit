# followup_verify_report

STATUS: **WARN**

- generated_at: 2026-02-10T04:08:46+00:00
- scanner: rg
- mode: full
- tokens_total: 2
- tokens_with_hits: 2
- hits_total: 5
- total_hits_estimate: 5

## Top Tokens
- `prompt-dsl-system/tools/_tmp_verify_followup/old/path`: hits=3
- `prompt-dsl-system/tools/_tmp_verify_followup/old/path/FooService.java`: hits=2

## Hit Samples
- `prompt-dsl-system/tools/_tmp_verify_followup/out_pass/followup_verify_report.json:13` token=`prompt-dsl-system/tools/_tmp_verify_followup/old/path/FooService.java` group=exact_paths :: "prompt-dsl-system/tools/_tmp_verify_followup/old/path/FooService.java"
- `prompt-dsl-system/tools/_tmp_verify_followup/README.md:1` token=`prompt-dsl-system/tools/_tmp_verify_followup/old/path/FooService.java` group=exact_paths :: prompt-dsl-system/tools/_tmp_verify_followup/old/path/FooService.java
- `prompt-dsl-system/tools/_tmp_verify_followup/out_pass/followup_verify_report.json:13` token=`prompt-dsl-system/tools/_tmp_verify_followup/old/path` group=old_dirs :: "prompt-dsl-system/tools/_tmp_verify_followup/old/path/FooService.java"
- `prompt-dsl-system/tools/_tmp_verify_followup/out_pass/followup_verify_report.json:16` token=`prompt-dsl-system/tools/_tmp_verify_followup/old/path` group=old_dirs :: "prompt-dsl-system/tools/_tmp_verify_followup/old/path"
- `prompt-dsl-system/tools/_tmp_verify_followup/README.md:1` token=`prompt-dsl-system/tools/_tmp_verify_followup/old/path` group=old_dirs :: prompt-dsl-system/tools/_tmp_verify_followup/old/path/FooService.java

## Next
- Run apply-followup-fixes in plan mode and review patch.
- Manually review remaining low-volume hits.
- Re-run verify-followup-fixes after adjustments.
