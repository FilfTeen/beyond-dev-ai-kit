# Hongzhi Company Constitution (Execution Rules)

Scope binding: this constitution is only for company-domain work in `prompt-dsl-system/**`.

## Rule 01 - Company Domain Isolation

- Rule: execution policy is company-scoped only; do not propagate into personal/global systems.
- Exception: user explicitly requests cross-system synchronization in writing.
- Check: changed files remain under `prompt-dsl-system/**`.
- Escalation: if task requires external policy injection, pause and ask user.
- Rollback: revert changed policy files to baseline snapshots.

## Rule 02 - Module Boundary Is Mandatory

- Rule: edits must stay within `allowed_module_root`.
- Exception: scan-only/risk-only outputs when boundary is missing.
- Check: `ops_guard.py --allowed-root <...>` pass required.
- Escalation: missing boundary => stop edits and request boundary.
- Rollback: revert out-of-scope files and regenerate scoped plan.

## Rule 03 - Forbidden Paths Hard Stop

- Rule: `/sys`, `/error`, `/util`, `/vote` are forbidden by default.
- Exception: user explicitly lifts restriction for a named path.
- Check: forbidden path violations in `ops_guard_report.json` must be empty.
- Escalation: any forbidden dependency touch requires user decision.
- Rollback: restore forbidden-path edits immediately.

## Rule 04 - Dependency Strategy Priority

- Rule: choose route in order `compat` > `self-contained` > `minimal-invasive`.
- Exception: higher-priority route provably violates hard constraints.
- Check: artifact contains route A/B comparison and selected route reason.
- Escalation: if no route fits constraints, request user override.
- Rollback: revert selected route and apply next valid higher-priority route.

## Rule 05 - Fact-First, No Guessing

- Rule: never invent names/fields/routes/tables/logic.
- Exception: none.
- Check: evidence scan section exists before change proposal.
- Escalation: unknown facts => output required-info checklist and pause edits.
- Rollback: discard outputs based on assumptions and re-scan.

## Rule 06 - Impact Tree Before Change

- Rule: produce tree analysis before write actions.
- Exception: pure report-only task with zero edits.
- Check: `A*_impact_tree.md` exists.
- Escalation: unresolved impact dependencies => ask user for scope clarification.
- Rollback: revert edits made without impact tree; regenerate tree first.

## Rule 07 - High-Risk Alarm

- Rule: high-risk actions must be explicitly flagged.
- Exception: none.
- Check: `risks[]` includes level/why/impact/mitigation/rollback.
- Escalation: high risk + low evidence requires user approval.
- Rollback: apply immediate rollback plan and freeze further edits.

## Rule 08 - Self-Monitor Loop Detection

- Rule: detect loops (`same file >3 edits` or `same failure >2`).
- Exception: user-approved iterative experiment loop.
- Check: self-monitor artifact includes loop status and evidence source.
- Escalation: loop detected => mandatory pause + root-cause rescan.
- Rollback: rollback partial loop changes before retry.

## Rule 09 - Auto Rollback on Loop

- Rule: loop signal triggers rollback-first behavior.
- Exception: user explicitly asks to continue without rollback.
- Check: `A*_rollback_plan.md` includes loop-trigger path.
- Escalation: if rollback safety is uncertain, request user intervention.
- Rollback: restore baseline and restart in conservative mode.

## Rule 10 - SQL Portability First

- Rule: SQL output defaults to portable SQL.
- Exception: explicit vendor-specific requirement with evidence.
- Check: sql policy declares `prefer_portable_sql=true`.
- Escalation: vendor lock-in path must be justified to user.
- Rollback: revert vendor-only patch and provide portable fallback.

## Rule 11 - Dual SQL When Needed

- Rule: non-portable requirement must output Oracle+MySQL dual SQL.
- Exception: user confirms single-dialect acceptance.
- Check: artifacts include dual SQL outputs and routing rule.
- Escalation: single-dialect only path needs user confirmation.
- Rollback: retract incomplete single-dialect delivery and regenerate dual output.

## Rule 12 - Pipeline Handoff Contract

- Rule: each step must include `context_id`, `trace_id`, `input_artifact_refs`.
- Exception: none.
- Check: `validate` passes and run plans show handoff fields in every step.
- Escalation: ambiguous artifact linkage requires user mapping input.
- Rollback: regenerate run plan with corrected artifact refs.

## Rule 13 - Job Closure Package

- Rule: closure must include README/notes update, change ledger, cleanup report.
- Exception: user explicitly waives document updates.
- Check: `A*_change_ledger.md` and `A*_cleanup_report.md` exist.
- Escalation: unknown doc target path => request user location.
- Rollback: remove incomplete closure output and regenerate full closure pack.

## Rule 14 - Tooling Gates Required

- Rule: pre/post gates are mandatory (`validate`, `ops_guard`; plus `merged_guard` for SQL merged deliveries).
- Exception: read-only exploration with no artifact generation.
- Check: JSON reports exist and gate result is pass.
- Escalation: gate failure blocks further release actions.
- Rollback: restore baseline files and re-run gates.

## Rule 15 - Recoverability

- Rule: all major changes must be reversible via snapshot + deprecated archive.
- Exception: none.
- Check: baseline snapshots, deprecated mapping, rollback instructions all present.
- Escalation: unclear rollback path => stop and ask user.
- Rollback: execute `ROLLBACK_INSTRUCTIONS.md` procedure.

## Rule 16 - Bypass Environment Variable Governance

- Rule: `HONGZHI_ALLOW_RUN_WITHOUT_MODULE_PATH=1` bypass is **only** permitted for:
  - Pipelines whose every step uses mode `meta` or `governance` (治理类 pipeline).
  - The pipeline's `allowed_module_root` or `module_path` must be `prompt-dsl-system` (self-referential治理).
  - Example: `pipeline_skill_creator.md` qualifies because it only modifies DSL system internal files.
- Prohibited usage:
  - Any pipeline that modifies business code, module code, SQL scripts, or frontend files **outside** `prompt-dsl-system/**`.
  - Any pipeline using modes `code`, `sql`, `frontend`, `process`, `release`.
  - Using bypass to circumvent `ops_guard.py` forbidden-path enforcement.
- Audit requirement:
  - When bypass is used, the closure artifacts (`A*_change_ledger.md`) must explicitly record: "bypass=HONGZHI_ALLOW_RUN_WITHOUT_MODULE_PATH=1, reason=<治理类pipeline>, scope=prompt-dsl-system/**".
  - Periodic audit: team lead reviews bypass usage in change ledgers quarterly.
- Escalation: unauthorized bypass usage => immediate rollback + incident report.
- Rollback: revert all changes made under unauthorized bypass and re-run with proper boundary.
