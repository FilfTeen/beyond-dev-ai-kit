# HONGZHI Task Operating Requirements (Authoritative)

This document is the authoritative operating profile for this kit in 博彦泓智科技（上海）有限公司 tasks.

## Scope & Activation

1. This kit is active only for 博彦泓智科技（上海）有限公司 development tasks.
2. Typical project style is property-management systems; project names often use pinyin initials (for example `xywygl`).
3. Existing systems are commonly legacy stacks (Java 8 / Spring Boot / LayUI and related traditional patterns), so compatibility-first delivery is required.

## Boundary & Safety Control

1. The user-defined module is the maximum default boundary per task.
2. Forbidden by default: `/sys`, `/error`, `/util`, `/vote`, and non-owned assets.
3. When strong dependency exists, decision order must be:
   1) compatibility first,
   2) self-contained rewrite-and-use,
   3) minimal invasive patch.
4. Route choice must consider risk, effort, quality, efficiency, and return.

## Framework-First Integration

1. Before implementation, scan and understand framework flow and dependencies (including workflow nodes such as activiti, system components, lifecycle/security/guards).
2. Prefer framework-native components first (exception/security/assert/state/generator mechanisms).
3. If framework cannot satisfy or is defective, apply the decision order above.

## SQL & Compatibility

1. Prefer portable/common SQL.
2. For non-portable sections, provide Oracle + MySQL dual SQL.
3. Ensure surrounding business logic code remains compatible.

## Proactive Engineering Duties

1. Proactively evaluate code quality, efficiency, and data security.
2. At decision branches, recommend best route with explicit tradeoffs.
3. Near closure or during exploration, proactively provide optimization/fix suggestions.
4. After completion, update module docs (README/structure docs), output work log, and clean redundant artifacts.

## Global Awareness, Tree Analysis, and Bug-Fix Principle

1. Keep real-time awareness of assets, ownership, and system dependencies.
2. Perform tree-impact analysis before edits; widen scanning under uncertainty.
3. For bug fixes, prioritize full-chain correctness over “code runs” only.
4. Escalate to user intervention on high-risk paths.

## Self-Monitoring & Correction

1. Detect abnormal loops (ineffective repeated edits, wrong target files, oscillation).
2. Stop, rescan, rollback wrong direction, recalibrate, then continue.

## Naming & Development Style

1. Team standard first; personal style applies only when correctness/consistency is preserved.
2. Naming is a hard requirement: English, short, semantic, globally aligned.
3. Prefer C++-influenced discipline:
   - types/classes/interfaces: `UpperCamelCase`
   - functions/helpers: align module dominant style; internal fallback `lower_snake_case`
   - constants: `UPPER_SNAKE_CASE`
   - booleans: `is_*`, `has_*`, `can_*`
   - SQL identifiers/aliases/DB fields: `lower_snake_case`

## Ambiguous Prompt Handling

1. For clear goals with vague prompts, execute minimal-scope changes only.
2. No broad unrelated refactors.
3. This does not weaken required tree-impact/full-chain analysis.

## Stack Knowledge Base

1. Build and maintain per-project stack profiles via scanner tooling.
2. Use discovered stack facts in delivery decisions.
3. While technology is not hard-limited in principle, new technology choices must be justified against compatibility and delivery value.

## Fact-First / Anti-Hallucination

1. No guessing critical logic, schema, symbols, or names.
2. If key facts are missing, scan first or escalate to user.
3. Block speculative edits when correctness-critical facts are unknown.

## Reuse / Migration / PM Mode

1. Property-management systems are highly reusable; controlled cross-project reuse/migration is allowed when user authorizes references.
2. Support PM-mode outputs: requirement/bid parsing, business/flow clarification, prototype-oriented artifacts.

## Quality Bar

1. Deliver concise, efficient, elegant, modern, maintainable implementations.
2. Keep formatting discipline and useful comments.
