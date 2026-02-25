# beyond-dev-ai-kit Makefile
# Common commands for development workflow.

SHELL := /bin/bash
PYTHON := /usr/bin/python3
REPO_ROOT := .
TOOLS := prompt-dsl-system/tools

.PHONY: help validate doctor release-check test test-unit test-golden test-fuzz test-mutation \
        selfcheck baseline-rebuild baseline-refresh promotion-matrix promotion-matrix-strict \
        docs-facts deployed-ref runtime-outputs double-run-consistency closure naming-check clean pressure lint

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── Core Gates ───

validate: ## Run full validate pipeline
	$(TOOLS)/run.sh validate -r $(REPO_ROOT) -m prompt-dsl-system

selfcheck: ## Run quality selfcheck scorecard
	$(PYTHON) $(TOOLS)/kit_selfcheck.py --repo-root $(REPO_ROOT) \
	  --out-json $(TOOLS)/kit_selfcheck_report.json \
	  --out-md $(TOOLS)/kit_selfcheck_report.md

doctor: baseline-rebuild promotion-matrix-strict validate selfcheck ## Full doctor chain (baseline->matrix->validate->selfcheck)

release-check: baseline-rebuild promotion-matrix-strict docs-facts deployed-ref runtime-outputs ## Release readiness chain (repo-wide validate + selfcheck + golden)
	$(TOOLS)/run.sh validate -r $(REPO_ROOT) -m .
	$(PYTHON) $(TOOLS)/kit_selfcheck.py --repo-root $(REPO_ROOT) \
	  --out-json $(TOOLS)/kit_selfcheck_report.json \
	  --out-md $(TOOLS)/kit_selfcheck_report.md
	$(PYTHON) $(TOOLS)/double_run_consistency_guard.py --repo-root $(REPO_ROOT)
	bash $(TOOLS)/golden_path_regression.sh --repo-root $(REPO_ROOT) \
	  --tmp-dir _regression_tmp_local --clean-tmp

# ─── Testing ───

test: test-unit test-golden test-fuzz test-mutation ## Run all tests
	@echo "ALL TESTS PASSED"

test-unit: ## Run unit tests
	$(PYTHON) -m unittest discover -s prompt-dsl-system/tools/tests -v

test-golden: ## Run golden path regression (172 checks)
	bash $(TOOLS)/golden_path_regression.sh --repo-root $(REPO_ROOT) \
	  --tmp-dir _regression_tmp_local --clean-tmp

test-fuzz: ## Run fuzz testing (1000 iterations)
	$(PYTHON) $(TOOLS)/fuzz_contract_pipeline_gate.py \
	  --repo-root $(REPO_ROOT) --iterations 1000 --seed 42

test-mutation: ## Run mutation resilience guard
	$(PYTHON) $(TOOLS)/gate_mutation_guard.py --repo-root $(REPO_ROOT)

pressure: ## Run pressure / latency budget tests
	$(PYTHON) $(TOOLS)/performance_budget_guard.py --repo-root $(REPO_ROOT)
	$(PYTHON) -m unittest prompt-dsl-system.tools.tests.intent_router.test_intent_router.IntentRouterTest.test_route_latency_budget

# ─── Baselines ───

baseline-rebuild: ## Rebuild all baselines in strict order (trust→provenance→manifest)
	bash $(TOOLS)/baseline_rebuild_all.sh --repo-root $(REPO_ROOT)

baseline-refresh: ## Refresh FACT_BASELINE summary counters
	$(PYTHON) $(TOOLS)/fact_baseline_refresh.py --repo-root $(REPO_ROOT)

promotion-matrix: ## Generate staging skill promotion readiness matrix
	$(PYTHON) $(TOOLS)/skill_promotion_matrix.py --repo-root $(REPO_ROOT)

promotion-matrix-strict: ## Fail if any staging skill is still pending
	$(PYTHON) $(TOOLS)/skill_promotion_matrix.py --repo-root $(REPO_ROOT) --fail-on-pending

docs-facts: ## Validate README/FACT key counters against source-of-truth
	$(PYTHON) $(TOOLS)/docs_facts_guard.py --repo-root $(REPO_ROOT)

deployed-ref: ## Validate all deployed skills are referenced by pipelines
	$(PYTHON) $(TOOLS)/deployed_skill_ref_guard.py --repo-root $(REPO_ROOT)

runtime-outputs: ## Ensure runtime output files are not tracked by git
	$(PYTHON) $(TOOLS)/runtime_outputs_tracking_guard.py --repo-root $(REPO_ROOT)

double-run-consistency: ## Verify validate/selfcheck are idempotent for tracked diff
	$(PYTHON) $(TOOLS)/double_run_consistency_guard.py --repo-root $(REPO_ROOT)

closure: ## Run delivery closure guard
	$(PYTHON) $(TOOLS)/delivery_closure_guard.py --repo-root $(REPO_ROOT)

naming-check: ## Run C++-aligned naming guard (changed Java files)
	$(PYTHON) $(TOOLS)/cpp_naming_guard.py --repo-root $(REPO_ROOT) --mode changed

# ─── Lint ───

lint: ## Run syntax checks on all Python + Shell files
	$(PYTHON) $(TOOLS)/tool_syntax_guard.py --repo-root $(REPO_ROOT)

# ─── Cleanup ───

clean: ## Remove regression temp files and caches
	rm -rf _regression_tmp/ _regression_tmp_local/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
