# beyond-dev-ai-kit — GitHub Copilot Instructions

## Project Overview

This repository contains **beyond-dev-ai-kit** (v1.3.0), a governed prompt/DSL/skill/pipeline
toolkit scoped to 博彦泓智科技（上海）有限公司 (Beyondsoft Hongzhi Technology).
It provides automated governance, quality gates, and AI-assisted development tooling
for Java 8 / Spring Boot property management systems.

## Mandatory First Step

Before any task, read `AGENTS.md` at the repository root for the complete intent-routing
protocol and execution rules.

## Key Architecture

- **00_conventions/**: 14 governance documents (Constitution with 50 rules, Compliance Matrix, etc.)
- **04_ai_pipeline_orchestration/**: 15 pipelines (bugfix, SQL migration, release, etc.)
- **05_skill_registry/**: 17 skills (code/sql/frontend/process/release/governance/docs/test/security)
- **tools/**: 180+ Python/Shell scripts for validation, integrity, and pipeline execution

## Intent Routing

Route natural-language requests to the best pipeline:

```bash
./prompt-dsl-system/tools/run.sh intent -r . --goal "<user_request>"
```

## Coding Standards

- Python: stdlib-only, type hints required, zero external dependencies
- Java: CPP_STYLE_NAMING.md conventions (UpperCamelCase classes, lowerCamelCase methods)
- SQL: Universal SQL first; Oracle + MySQL dual-stack fallback (see SQL_COMPAT_STRATEGY.md)
- Security: never print secrets; redact password/token/jdbc fields

## Boundary Rules

- Use `-m prompt-dsl-system` for governance/meta pipelines
- Require explicit `module_path` for business-code pipelines
- Forbidden paths: `/sys`, `/error`, `/util`, `/vote`
- Always validate: `./prompt-dsl-system/tools/run.sh validate -r .`
