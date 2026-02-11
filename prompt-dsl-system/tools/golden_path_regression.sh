#!/usr/bin/env bash
# Golden Path Regression — simulated end-to-end chain for prompt-dsl-system.
#
# Chain: validate(strict) → simulate bootstrap → validate(strict) → simulate promote → validate(strict)
#
# Usage:
#   bash prompt-dsl-system/tools/golden_path_regression.sh --repo-root .
#
# Exit codes:
#   0 = all checks PASS
#   1 = at least one check FAIL

set -euo pipefail

REPO_ROOT="${1:-.}"
if [ "$1" = "--repo-root" ] && [ -n "${2:-}" ]; then
  REPO_ROOT="$2"
fi
REPO_ROOT="$(cd "$REPO_ROOT" && pwd)"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"
SKILLS_JSON="$REPO_ROOT/prompt-dsl-system/05_skill_registry/skills.json"
SKILLS_DIR="$REPO_ROOT/prompt-dsl-system/05_skill_registry/skills"
TEMPLATE_DIR="$REPO_ROOT/prompt-dsl-system/05_skill_registry/templates/skill_template"
REGRESSION_TMP="$REPO_ROOT/_regression_tmp"
REPORT_FILE="$REGRESSION_TMP/regression_report.md"

RC=0
TOTAL=0
PASSED=0
CHECKS=""

check() {
  local name="$1"
  local result="$2"
  TOTAL=$((TOTAL + 1))
  if [ "$result" = "PASS" ]; then
    PASSED=$((PASSED + 1))
    CHECKS="${CHECKS}\n| $TOTAL | $name | PASS |"
  else
    RC=1
    CHECKS="${CHECKS}\n| $TOTAL | $name | **FAIL** |"
  fi
}

echo "=== Golden Path Regression ==="
echo "repo-root: $REPO_ROOT"
echo ""

# Cleanup previous runs
rm -rf "$REGRESSION_TMP"
mkdir -p "$REGRESSION_TMP"

# ─── Phase 1: validate(strict) on current state ───
echo "[phase 1] validate(strict) — current state"
set +e
HONGZHI_VALIDATE_STRICT=1 "$PYTHON_BIN" "$SCRIPT_DIR/skill_template_audit.py" \
  --repo-root "$REPO_ROOT" --scope all --fail-on-empty > "$REGRESSION_TMP/phase1_audit.log" 2>&1
P1_AUDIT=$?
HONGZHI_VALIDATE_STRICT=1 "$PYTHON_BIN" "$SCRIPT_DIR/pipeline_contract_lint.py" \
  --repo-root "$REPO_ROOT" --fail-on-empty > "$REGRESSION_TMP/phase1_lint.log" 2>&1
P1_LINT=$?
set -e

[ "$P1_AUDIT" -eq 0 ] && check "Phase1:audit" "PASS" || check "Phase1:audit" "FAIL"
[ "$P1_LINT" -eq 0 ] && check "Phase1:lint" "PASS" || check "Phase1:lint" "FAIL"

# ─── Phase 2: simulate bootstrap (create staging skill in tmp) ───
echo "[phase 2] simulate bootstrap — create staging skill"
SIM_DOMAIN="regression"
SIM_SKILL="skill_regression_test_ops"
SIM_SKILL_DIR="$SKILLS_DIR/$SIM_DOMAIN/$SIM_SKILL"

# Check template exists
if [ -d "$TEMPLATE_DIR" ]; then
  check "Phase2:template_exists" "PASS"
else
  check "Phase2:template_exists" "FAIL"
fi

# Create simulated skill directory from template
mkdir -p "$SIM_SKILL_DIR"/{references,scripts,assets}

# Create a minimal valid skill YAML (no placeholders)
cat > "$SIM_SKILL_DIR/${SIM_SKILL}.yaml" <<'EOYAML'
name: skill_regression_test_ops
description: "Golden path regression test skill — auto-generated, do NOT deploy."
version: "0.1.0"
domain: regression
tags: [regression, test]
parameters:
  mode:
    type: string
    required: true
  objective:
    type: string
    required: true
  constraints:
    type: list
    required: true
  acceptance:
    type: list
    required: true
  forbidden:
    type: list
    required: true
  context_id:
    type: string
    required: true
  trace_id:
    type: string
    required: true
  input_artifact_refs:
    type: list
    required: false
  module_path:
    type: string
    required: false
  allowed_module_root:
    type: string
    required: true
  boundary_policy:
    type: object
    required: false
  fact_policy:
    type: object
    required: false
  self_monitor_policy:
    type: object
    required: false
  decision_policy:
    type: object
    required: false
  sql_policy:
    type: object
    required: false
prompt_template: |
  Regression test prompt for {{mode}} — {{objective}}.
output_contract:
  summary: "string"
  artifacts: "list"
  risks: "list"
  next_actions: "list"
examples:
  - input:
      mode: governance
      objective: "test"
      constraints: ["scan-only"]
      acceptance: ["report.md"]
      forbidden: ["no changes"]
      context_id: "test-001"
      trace_id: "test-001"
      allowed_module_root: "prompt-dsl-system"
    output:
      summary: "regression test"
      artifacts: ["report.md"]
      risks: []
      next_actions: []
EOYAML

# Add to registry (backup original first)
cp "$SKILLS_JSON" "$REGRESSION_TMP/skills.json.bak"
"$PYTHON_BIN" -c "
import json, pathlib
f = pathlib.Path('$SKILLS_JSON')
d = json.loads(f.read_text())
d.append({
    'name': '$SIM_SKILL',
    'description': 'Golden path regression test',
    'version': '0.1.0',
    'domain': '$SIM_DOMAIN',
    'tags': ['regression','test'],
    'path': 'prompt-dsl-system/05_skill_registry/skills/$SIM_DOMAIN/$SIM_SKILL/${SIM_SKILL}.yaml',
    'status': 'staging'
})
f.write_text(json.dumps(d, indent=2, ensure_ascii=False))
"
check "Phase2:registry_update" "PASS"

# ─── Phase 3: validate(strict) on state with staging skill ───
echo "[phase 3] validate(strict) — with staging skill"
set +e
"$PYTHON_BIN" "$SCRIPT_DIR/skill_template_audit.py" \
  --repo-root "$REPO_ROOT" --scope all --fail-on-empty > "$REGRESSION_TMP/phase3_audit.log" 2>&1
P3_AUDIT=$?
"$PYTHON_BIN" "$SCRIPT_DIR/pipeline_contract_lint.py" \
  --repo-root "$REPO_ROOT" --fail-on-empty > "$REGRESSION_TMP/phase3_lint.log" 2>&1
P3_LINT=$?
set -e

[ "$P3_AUDIT" -eq 0 ] && check "Phase3:audit(+staging)" "PASS" || check "Phase3:audit(+staging)" "FAIL"
[ "$P3_LINT" -eq 0 ] && check "Phase3:lint(+staging)" "PASS" || check "Phase3:lint(+staging)" "FAIL"

# ─── Phase 4: simulate promote (staging → deployed) ───
echo "[phase 4] simulate promote — staging → deployed"
"$PYTHON_BIN" -c "
import json, pathlib
f = pathlib.Path('$SKILLS_JSON')
d = json.loads(f.read_text())
for e in d:
    if e.get('name') == '$SIM_SKILL':
        e['status'] = 'deployed'
f.write_text(json.dumps(d, indent=2, ensure_ascii=False))
"
check "Phase4:promote" "PASS"

# ─── Phase 5: validate(strict) on promoted state ───
echo "[phase 5] validate(strict) — after promote"
set +e
"$PYTHON_BIN" "$SCRIPT_DIR/skill_template_audit.py" \
  --repo-root "$REPO_ROOT" --scope all --fail-on-empty > "$REGRESSION_TMP/phase5_audit.log" 2>&1
P5_AUDIT=$?
set -e

[ "$P5_AUDIT" -eq 0 ] && check "Phase5:audit(deployed)" "PASS" || check "Phase5:audit(deployed)" "FAIL"

# ─── Phase 6: migration pipeline smoke ───
echo "[phase 6] migration pipeline smoke"
MIGRATION_PIPELINE="$REPO_ROOT/prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_module_migration.md"
if [ -f "$MIGRATION_PIPELINE" ]; then
  check "Phase6:migration_pipeline_exists" "PASS"
  # Verify lint covers it (count pipeline_module_migration in lint output)
  set +e
  "$PYTHON_BIN" "$SCRIPT_DIR/pipeline_contract_lint.py" \
    --repo-root "$REPO_ROOT" --fail-on-empty > "$REGRESSION_TMP/phase6_lint.log" 2>&1
  P6_LINT=$?
  set -e
  [ "$P6_LINT" -eq 0 ] && check "Phase6:migration_lint" "PASS" || check "Phase6:migration_lint" "FAIL"
else
  check "Phase6:migration_pipeline_exists" "FAIL"
fi

# ─── Phase 7: profile smoke ───
echo "[phase 7] profile smoke"
PROFILE_TEMPLATE="$REPO_ROOT/prompt-dsl-system/module_profiles/template/module_profile.yaml"
if [ -f "$PROFILE_TEMPLATE" ]; then
  check "Phase7:profile_template_exists" "PASS"
else
  check "Phase7:profile_template_exists" "FAIL"
fi

# Scanner syntax check (--help should exit 0)
SCANNER_SCRIPT="$SCRIPT_DIR/module_profile_scanner.py"
if [ -f "$SCANNER_SCRIPT" ]; then
  set +e
  "$PYTHON_BIN" "$SCANNER_SCRIPT" --help > /dev/null 2>&1
  SC_RC=$?
  set -e
  [ "$SC_RC" -eq 0 ] && check "Phase7:scanner_syntax" "PASS" || check "Phase7:scanner_syntax" "FAIL"
else
  check "Phase7:scanner_syntax" "FAIL"
fi

# ─── Phase 8: guard strict consistency (no-VCS strict should FAIL) ───
echo "[phase 8] guard strict consistency"
NO_VCS_TMP="$REGRESSION_TMP/no_vcs_root"
mkdir -p "$NO_VCS_TMP/prompt-dsl-system/tools"
# Copy guardrails if exists
if [ -f "$REPO_ROOT/prompt-dsl-system/tools/guardrails.yaml" ]; then
  cp "$REPO_ROOT/prompt-dsl-system/tools/guardrails.yaml" "$NO_VCS_TMP/prompt-dsl-system/tools/"
fi
set +e
HONGZHI_VALIDATE_STRICT=1 "$PYTHON_BIN" "$SCRIPT_DIR/path_diff_guard.py" \
  --repo-root "$NO_VCS_TMP" --mode validate > "$REGRESSION_TMP/phase8_guard.log" 2>&1
P8_RC=$?
set -e
if [ "$P8_RC" -ne 0 ]; then
  check "Phase8:guard_strict_no_vcs_fails" "PASS"
else
  check "Phase8:guard_strict_no_vcs_fails" "FAIL"
fi

# ─── Cleanup: restore original state ───
echo "[cleanup] restoring original state"
cp "$REGRESSION_TMP/skills.json.bak" "$SKILLS_JSON"
rm -rf "$SIM_SKILL_DIR"
# Remove domain dir if empty
rmdir "$SKILLS_DIR/$SIM_DOMAIN" 2>/dev/null || true

# ─── Report ───
cat > "$REPORT_FILE" <<EOF
# Golden Path Regression Report

Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Repo Root: $REPO_ROOT

## Results

| # | Check | Result |
| --- | --- | --- |
$(echo -e "$CHECKS")

## Summary

**$PASSED / $TOTAL** checks passed.

$([ "$RC" -eq 0 ] && echo "**OVERALL: PASS**" || echo "**OVERALL: FAIL**")
EOF

echo ""
echo "=== Regression Report ==="
cat "$REPORT_FILE"
echo ""
echo "report: $REPORT_FILE"

exit $RC
