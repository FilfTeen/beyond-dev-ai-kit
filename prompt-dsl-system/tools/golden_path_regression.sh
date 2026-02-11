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

extract_machine_path() {
  local line="$1"
  "$PYTHON_BIN" - "$line" <<'PY'
import shlex
import sys

line = sys.argv[1] if len(sys.argv) > 1 else ""
path = ""
try:
    tokens = shlex.split(line)
except ValueError:
    tokens = line.split()
for token in tokens[1:]:
    if token.startswith("path="):
        path = token.split("=", 1)[1]
        break
if not path and len(tokens) > 1:
    path = tokens[1]
print(path)
PY
}

snapshot_sig() {
  "$PYTHON_BIN" - "$@" <<'PY'
import hashlib
import pathlib
import sys

items = []
for root in sys.argv[1:]:
    p = pathlib.Path(root)
    if not p.exists():
        items.append(f"missing:{p}")
        continue
    for fp in sorted([x for x in p.rglob("*") if x.is_file()]):
        try:
            st = fp.stat()
            rel = fp.relative_to(p)
            items.append(f"{p}|{rel}|{st.st_size}|{st.st_mtime_ns}")
        except OSError:
            items.append(f"{p}|{fp}|stat_error")
joined = "\n".join(items)
print(hashlib.sha256(joined.encode("utf-8")).hexdigest())
PY
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

# ─── Phase 9: roots_discover smoke ───
echo "[phase 9] roots_discover smoke"
ROOTS_DISCOVER="$SCRIPT_DIR/module_roots_discover.py"
if [ -f "$ROOTS_DISCOVER" ]; then
  set +e
  "$PYTHON_BIN" "$ROOTS_DISCOVER" --help > /dev/null 2>&1
  RD_RC=$?
  set -e
  [ "$RD_RC" -eq 0 ] && check "Phase9:roots_discover_syntax" "PASS" || check "Phase9:roots_discover_syntax" "FAIL"
else
  check "Phase9:roots_discover_syntax" "FAIL"
fi

# Scanner should accept --allowed-module-root as optional now
set +e
"$PYTHON_BIN" "$SCANNER_SCRIPT" --help 2>&1 | grep -q "allowed-module-root"
SC_MULTI_RC=$?
set -e
[ "$SC_MULTI_RC" -eq 0 ] && check "Phase9:scanner_multi_root_support" "PASS" || check "Phase9:scanner_multi_root_support" "FAIL"

# ─── Phase 10: structure_discover smoke ───
echo "[phase 10] structure_discover smoke"
STRUCT_DISCOVER="$SCRIPT_DIR/structure_discover.py"
if [ -f "$STRUCT_DISCOVER" ]; then
  set +e
  "$PYTHON_BIN" "$STRUCT_DISCOVER" --help > /dev/null 2>&1
  SD_RC=$?
  set -e
  [ "$SD_RC" -eq 0 ] && check "Phase10:structure_discover_syntax" "PASS" || check "Phase10:structure_discover_syntax" "FAIL"
else
  check "Phase10:structure_discover_syntax" "FAIL"
fi
# Check concurrent support (ThreadPoolExecutor import)
set +e
grep -q "ThreadPoolExecutor" "$STRUCT_DISCOVER" 2>/dev/null
SD_CONC_RC=$?
set -e
[ "$SD_CONC_RC" -eq 0 ] && check "Phase10:structure_discover_concurrent" "PASS" || check "Phase10:structure_discover_concurrent" "FAIL"

# ─── Phase 11: cross_project_diff smoke ───
echo "[phase 11] cross_project_diff smoke"
CROSS_DIFF="$SCRIPT_DIR/cross_project_structure_diff.py"
if [ -f "$CROSS_DIFF" ]; then
  set +e
  "$PYTHON_BIN" "$CROSS_DIFF" --help > /dev/null 2>&1
  CD_RC=$?
  set -e
  [ "$CD_RC" -eq 0 ] && check "Phase11:cross_project_diff_syntax" "PASS" || check "Phase11:cross_project_diff_syntax" "FAIL"
else
  check "Phase11:cross_project_diff_syntax" "FAIL"
fi

# ─── Phase 12: auto_module_discover smoke ───
echo "[phase 12] auto_module_discover smoke"
AUTO_DISCOVER="$SCRIPT_DIR/auto_module_discover.py"
if [ -f "$AUTO_DISCOVER" ]; then
  set +e
  "$PYTHON_BIN" "$AUTO_DISCOVER" --help > /dev/null 2>&1
  AD_RC=$?
  set -e
  [ "$AD_RC" -eq 0 ] && check "Phase12:auto_module_discover_syntax" "PASS" || check "Phase12:auto_module_discover_syntax" "FAIL"

  # Run on test fixtures — should find at least 1 candidate
  CASE1="$SCRIPT_DIR/_tmp_structure_cases/case1_standard"
  if [ -d "$CASE1" ]; then
    set +e
    AD_OUT=$("$PYTHON_BIN" "$AUTO_DISCOVER" --repo-root "$CASE1" --read-only 2>/dev/null)
    AD_RUN_RC=$?
    set -e
    if [ "$AD_RUN_RC" -eq 0 ] && echo "$AD_OUT" | grep -q "module_key"; then
      check "Phase12:auto_discover_finds_module" "PASS"
    else
      check "Phase12:auto_discover_finds_module" "FAIL"
    fi
  else
    check "Phase12:auto_discover_finds_module" "FAIL"
  fi
else
  check "Phase12:auto_module_discover_syntax" "FAIL"
  check "Phase12:auto_discover_finds_module" "FAIL"
fi

# ─── Phase 13: endpoint signature v2 smoke ───
echo "[phase 13] endpoint signature v2 smoke"
CASE2="$SCRIPT_DIR/_tmp_structure_cases/case2_classlevel"
CASE4="$SCRIPT_DIR/_tmp_structure_cases/case4_endpoint_miss"
CASE5="$SCRIPT_DIR/_tmp_structure_cases/case5_ambiguous_two_modules"
CASE6="$SCRIPT_DIR/_tmp_structure_cases/case6_maven_multi_module"
CASE7="$SCRIPT_DIR/_tmp_structure_cases/case7_nonstandard_java_root"
CASE8="$SCRIPT_DIR/_tmp_structure_cases/case8_composed_annotation"
if [ -d "$CASE2" ] && [ -f "$STRUCT_DISCOVER" ]; then
  set +e
  SD_OUT=$("$PYTHON_BIN" "$STRUCT_DISCOVER" --repo-root "$CASE2" --project-key test --module-key order --read-only 2>/dev/null)
  SD_EP_RC=$?
  set -e
  if [ "$SD_EP_RC" -eq 0 ] && echo "$SD_OUT" | grep -q "http_method"; then
    check "Phase13:endpoint_v2_extracts_method" "PASS"
  else
    check "Phase13:endpoint_v2_extracts_method" "FAIL"
  fi
else
  check "Phase13:endpoint_v2_extracts_method" "FAIL"
fi

# ─── Phase 14: cache incremental smoke ───
echo "[phase 14] cache incremental smoke"
if [ -d "$CASE1" ] && [ -f "$STRUCT_DISCOVER" ]; then
  # First run: cold cache
  CACHE_TMP="$REGRESSION_TMP/cache_test"
  mkdir -p "$CACHE_TMP"
  set +e
  T1_START=$(python3 -c "import time; print(time.time())")
  "$PYTHON_BIN" "$STRUCT_DISCOVER" --repo-root "$CASE1" --project-key test --module-key notice \
    --out "$CACHE_TMP/first.yaml" --out-root "$CACHE_TMP" > /dev/null 2>&1
  T1_END=$(python3 -c "import time; print(time.time())")
  # Second run: warm cache
  T2_START=$(python3 -c "import time; print(time.time())")
  S2_ERR=$("$PYTHON_BIN" "$STRUCT_DISCOVER" --repo-root "$CASE1" --project-key test --module-key notice \
    --out "$CACHE_TMP/second.yaml" --out-root "$CACHE_TMP" 2>&1 >/dev/null)
  T2_END=$(python3 -c "import time; print(time.time())")
  set -e
  # Check cache hit rate reported
  if echo "$S2_ERR" | grep -q "cache:"; then
    check "Phase14:cache_reports_stats" "PASS"
  else
    check "Phase14:cache_reports_stats" "FAIL"
  fi
  # Check output contains cache_stats
  if [ -f "$CACHE_TMP/second.yaml" ] && grep -q "cache_hit_files" "$CACHE_TMP/second.yaml"; then
    check "Phase14:cache_hit_in_output" "PASS"
  else
    check "Phase14:cache_hit_in_output" "FAIL"
  fi
  rm -rf "$CACHE_TMP"
else
  check "Phase14:cache_reports_stats" "FAIL"
  check "Phase14:cache_hit_in_output" "FAIL"
fi

PLUGIN="$SCRIPT_DIR/hongzhi_plugin.py"
PLUGIN_STATE="$REGRESSION_TMP/plugin_global_state"
mkdir -p "$PLUGIN_STATE"

# ─── Phase 15: plugin_discover_smoke ───
echo "[phase 15] plugin_discover_smoke"
if [ -f "$PLUGIN" ] && [ -d "$CASE1" ]; then
  PLUGIN_WS="$REGRESSION_TMP/plugin_ws_15"
  mkdir -p "$PLUGIN_WS"
  set +e
  HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" --help > /dev/null 2>&1
  PL_HELP_RC=$?
  set -e
  [ "$PL_HELP_RC" -eq 0 ] && check "Phase15:plugin_syntax" "PASS" || check "Phase15:plugin_syntax" "FAIL"

  set +e
  HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --workspace-root "$PLUGIN_WS" --global-state-root "$PLUGIN_STATE" 2>/dev/null
  PL_DISC_RC=$?
  set -e
  if [ "$PL_DISC_RC" -eq 0 ] && [ -f "$PLUGIN_WS"/*/discover/auto_discover.yaml ]; then
    check "Phase15:plugin_discover_output" "PASS"
  else
    # Try glob expansion more carefully
    FOUND_CAPS=$(find "$PLUGIN_WS" -name "capabilities.json" -type f 2>/dev/null | head -1)
    if [ -n "$FOUND_CAPS" ] && grep -q '"command": "discover"' "$FOUND_CAPS"; then
      check "Phase15:plugin_discover_output" "PASS"
    else
      check "Phase15:plugin_discover_output" "FAIL"
    fi
  fi
  rm -rf "$PLUGIN_WS"
else
  check "Phase15:plugin_syntax" "FAIL"
  check "Phase15:plugin_discover_output" "FAIL"
fi

# ─── Phase 16: plugin_read_only_contract ───
echo "[phase 16] plugin_read_only_contract"
if [ -f "$PLUGIN" ] && [ -d "$CASE1" ]; then
  # Create isolated copy of test project
  RO_TMP="$REGRESSION_TMP/ro_project"
  cp -R "$CASE1" "$RO_TMP"
  PLUGIN_WS="$REGRESSION_TMP/plugin_ws_16"
  mkdir -p "$PLUGIN_WS"

  # Take snapshot of file count before
  BEFORE_COUNT=$(find "$RO_TMP" -type f | wc -l | tr -d ' ')

  set +e
  HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$RO_TMP" --workspace-root "$PLUGIN_WS" --global-state-root "$PLUGIN_STATE" > /dev/null 2>&1
  PL_RO_RC=$?
  set -e

  # Take snapshot of file count after
  AFTER_COUNT=$(find "$RO_TMP" -type f | wc -l | tr -d ' ')

  if [ "$BEFORE_COUNT" = "$AFTER_COUNT" ] && [ "$PL_RO_RC" -eq 0 ]; then
    check "Phase16:plugin_read_only_contract" "PASS"
  else
    check "Phase16:plugin_read_only_contract" "FAIL"
  fi
  rm -rf "$RO_TMP" "$PLUGIN_WS"
else
  check "Phase16:plugin_read_only_contract" "FAIL"
fi

# ─── Phase 17: plugin_cache_warm_smoke ───
echo "[phase 17] plugin_cache_warm_smoke"
if [ -f "$PLUGIN" ] && [ -d "$CASE1" ]; then
  PLUGIN_WS="$REGRESSION_TMP/plugin_ws_17"
  mkdir -p "$PLUGIN_WS"
  # First run (cold)
  set +e
  HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --workspace-root "$PLUGIN_WS" --global-state-root "$PLUGIN_STATE" > /dev/null 2>&1
  # Second run (warm — reuses same workspace for cache)
  PL_OUT2=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --workspace-root "$PLUGIN_WS" --global-state-root "$PLUGIN_STATE" 2>/dev/null)
  PL_WARM_RC=$?
  set -e
  # Check capabilities.json exists in second run with cache stats
  FOUND_CAPS=$(find "$PLUGIN_WS" -name "capabilities.json" -type f 2>/dev/null | sort | tail -1)
  if [ -n "$FOUND_CAPS" ] && grep -q '"cache_hit_files"' "$FOUND_CAPS"; then
    check "Phase17:plugin_cache_warm" "PASS"
  else
    check "Phase17:plugin_cache_warm" "FAIL"
  fi
  rm -rf "$PLUGIN_WS"
else
  check "Phase17:plugin_cache_warm" "FAIL"
fi

# ─── Phase 18: plugin governance disabled-by-default ───
echo "[phase 18] plugin governance disabled-by-default"
if [ -f "$PLUGIN" ]; then
  set +e
  # Run WITHOUT HONGZHI_PLUGIN_ENABLE — should exit 10
  unset HONGZHI_PLUGIN_ENABLE 2>/dev/null || true
  "$PYTHON_BIN" "$PLUGIN" discover --repo-root "$CASE1" --global-state-root "$PLUGIN_STATE" > /dev/null 2>&1
  PL_GOV_RC=$?
  set -e
  if [ "$PL_GOV_RC" -eq 10 ]; then
    check "Phase18:plugin_governance_disabled" "PASS"
  else
    check "Phase18:plugin_governance_disabled" "FAIL"
  fi
else
  check "Phase18:plugin_governance_disabled" "FAIL"
fi


# ─── Phase 19: plugin governance extensions ───
echo "[phase 19] plugin governance extensions"
if [ -f "$PLUGIN" ]; then
  # 1. Module entry check
  set +e
  export PYTHONPATH="$REPO_ROOT/prompt-dsl-system/tools:${PYTHONPATH:-}"
  python3 -m hongzhi_ai_kit status > /dev/null 2>&1
  PL_MOD_RC=$?
  set -e
  if [ "$PL_MOD_RC" -eq 0 ]; then
    check "Phase19:plugin_module_entrypoint" "PASS"
  else
    check "Phase19:plugin_module_entrypoint" "FAIL"
  fi

  # Setup temp policy and repos for governance test
  GOV_TMP="$REGRESSION_TMP/gov_check"
  mkdir -p "$GOV_TMP/allowed_repo" "$GOV_TMP/denied_repo" "$GOV_TMP/blocked_repo"
  cat > "$GOV_TMP/policy.yaml" <<EOF
plugin:
  enabled: true
  allow_roots: ["$GOV_TMP/allowed_repo"]
  deny_roots: ["$GOV_TMP/denied_repo"]
EOF
  
  # 2. Blocked repo (not in allow_roots) -> exit 12
  set +e
  unset HONGZHI_PLUGIN_ENABLE 2>/dev/null || true
  # Note: passing --kit-root to point to policy.yaml
  "$PYTHON_BIN" "$PLUGIN" status --repo-root "$GOV_TMP/blocked_repo" --kit-root "$GOV_TMP" > /dev/null 2>&1
  RC_BLOCK=$?
  set -e
  if [ "$RC_BLOCK" -eq 12 ]; then
    check "Phase19:governance_allowlist_block" "PASS"
  else
    check "Phase19:governance_allowlist_block" "FAIL"
  fi

  # 3. Denied repo (in deny_roots) -> exit 11
  set +e
  "$PYTHON_BIN" "$PLUGIN" status --repo-root "$GOV_TMP/denied_repo" --kit-root "$GOV_TMP" > /dev/null 2>&1
  RC_DENY=$?
  set -e
  if [ "$RC_DENY" -eq 11 ]; then
    check "Phase19:governance_deny_block" "PASS"
  else
    check "Phase19:governance_deny_block" "FAIL"
  fi

  # 4. Permit token override -> exit 0
  set +e
  "$PYTHON_BIN" "$PLUGIN" status --repo-root "$GOV_TMP/blocked_repo" --kit-root "$GOV_TMP" --permit-token "SKS-BYPASS" > /dev/null 2>&1
  RC_PERMIT=$?
  set -e
  if [ "$RC_PERMIT" -eq 0 ]; then
    check "Phase19:permit_token_override" "PASS"
  else
    check "Phase19:permit_token_override" "FAIL"
  fi

  rm -rf "$GOV_TMP"
else
  check "Phase19:plugin_module_entrypoint" "FAIL"
fi

# ─── Phase 20: capability_index_smoke ───
echo "[phase 20] capability_index_smoke"
if [ -f "$PLUGIN" ] && [ -d "$CASE1" ]; then
  PLUGIN_WS="$REGRESSION_TMP/plugin_ws_20"
  rm -rf "$PLUGIN_WS"
  mkdir -p "$PLUGIN_WS"
  rm -rf "$PLUGIN_STATE"
  mkdir -p "$PLUGIN_STATE"

  set +e
  HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --workspace-root "$PLUGIN_WS" --global-state-root "$PLUGIN_STATE" > /dev/null 2>&1
  P20_RC=$?
  set -e

  P20_CHECK1=$("$PYTHON_BIN" - <<PY
import json, pathlib
import sys
case1 = pathlib.Path("$CASE1").resolve()
plugin = pathlib.Path("$PLUGIN")
state = pathlib.Path("$PLUGIN_STATE")
import importlib.util
sys.path.insert(0, str(pathlib.Path("$REPO_ROOT/prompt-dsl-system/tools")))
spec = importlib.util.spec_from_file_location("hongzhi_plugin", str(plugin))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
fp = mod.compute_project_fingerprint(case1)
idx = state / "capability_index.json"
ok = False
if idx.exists():
    data = json.loads(idx.read_text(encoding="utf-8"))
    ok = fp in data.get("projects", {})
print("1" if ok else "0")
PY
)
  if [ "$P20_RC" -eq 0 ] && [ "$P20_CHECK1" = "1" ]; then
    check "Phase20:capability_index_created" "PASS"
  else
    check "Phase20:capability_index_created" "FAIL"
  fi

  P20_CHECK2=$("$PYTHON_BIN" - <<PY
import json, pathlib
import sys
case1 = pathlib.Path("$CASE1").resolve()
plugin = pathlib.Path("$PLUGIN")
state = pathlib.Path("$PLUGIN_STATE")
import importlib.util
sys.path.insert(0, str(pathlib.Path("$REPO_ROOT/prompt-dsl-system/tools")))
spec = importlib.util.spec_from_file_location("hongzhi_plugin", str(plugin))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
fp = mod.compute_project_fingerprint(case1)
latest = state / fp / "latest.json"
ok = False
if latest.exists():
    data = json.loads(latest.read_text(encoding="utf-8"))
    ws = pathlib.Path(data.get("workspace", ""))
    ok = ws.exists()
print("1" if ok else "0")
PY
)
  if [ "$P20_CHECK2" = "1" ]; then
    check "Phase20:latest_pointer_created" "PASS"
  else
    check "Phase20:latest_pointer_created" "FAIL"
  fi
  rm -rf "$PLUGIN_WS"
else
  check "Phase20:capability_index_created" "FAIL"
  check "Phase20:latest_pointer_created" "FAIL"
fi

# ─── Phase 21: smart_reuse_smoke ───
echo "[phase 21] smart_reuse_smoke"
if [ -f "$PLUGIN" ] && [ -d "$CASE1" ]; then
  PLUGIN_WS="$REGRESSION_TMP/plugin_ws_21"
  rm -rf "$PLUGIN_WS"
  mkdir -p "$PLUGIN_WS"
  rm -rf "$PLUGIN_STATE"
  mkdir -p "$PLUGIN_STATE"

  set +e
  OUT1=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --workspace-root "$PLUGIN_WS" --global-state-root "$PLUGIN_STATE" 2>/dev/null)
  RC1=$?
  OUT2=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --workspace-root "$PLUGIN_WS" --global-state-root "$PLUGIN_STATE" \
    --smart --smart-max-age-seconds 9999 2>/dev/null)
  RC2=$?
  set -e

  if [ "$RC1" -eq 0 ] && [ "$RC2" -eq 0 ] && echo "$OUT2" | grep -q "smart_reused=1"; then
    check "Phase21:smart_reused_summary" "PASS"
  else
    check "Phase21:smart_reused_summary" "FAIL"
  fi

  P21_CHECK2=$("$PYTHON_BIN" - <<PY
import json, pathlib
ws = pathlib.Path("$PLUGIN_WS")
caps = sorted(ws.rglob("capabilities.json"))
if len(caps) < 2:
    print("0")
else:
    first = json.loads(caps[0].read_text(encoding="utf-8"))
    second = json.loads(caps[-1].read_text(encoding="utf-8"))
    reused = bool(second.get("smart", {}).get("reused"))
    t1 = float(first.get("metrics", {}).get("scan_time_s", 9999))
    t2 = float(second.get("metrics", {}).get("scan_time_s", 9999))
    ok = reused or (t2 <= t1 * 0.5)
    print("1" if ok else "0")
PY
)
  if [ "$P21_CHECK2" = "1" ]; then
    check "Phase21:smart_reuse_effective" "PASS"
  else
    check "Phase21:smart_reuse_effective" "FAIL"
  fi
  rm -rf "$PLUGIN_WS"
else
  check "Phase21:smart_reused_summary" "FAIL"
  check "Phase21:smart_reuse_effective" "FAIL"
fi

# ─── Phase 22: governance_no_state_write ───
echo "[phase 22] governance_no_state_write"
if [ -f "$PLUGIN" ] && [ -d "$CASE1" ]; then
  rm -rf "$PLUGIN_STATE"
  mkdir -p "$PLUGIN_STATE"
  BEFORE_SIG=$("$PYTHON_BIN" - <<PY
import pathlib
p = pathlib.Path("$PLUGIN_STATE/capability_index.json")
print(f"{int(p.stat().st_mtime_ns)}" if p.exists() else "missing")
PY
)
  set +e
  unset HONGZHI_PLUGIN_ENABLE 2>/dev/null || true
  "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --global-state-root "$PLUGIN_STATE" > /dev/null 2>&1
  P22_RC=$?
  set -e
  AFTER_SIG=$("$PYTHON_BIN" - <<PY
import pathlib
p = pathlib.Path("$PLUGIN_STATE/capability_index.json")
print(f"{int(p.stat().st_mtime_ns)}" if p.exists() else "missing")
PY
)
  if [ "$P22_RC" -eq 10 ] && [ "$BEFORE_SIG" = "$AFTER_SIG" ]; then
    check "Phase22:governance_no_state_write" "PASS"
  else
    check "Phase22:governance_no_state_write" "FAIL"
  fi
else
  check "Phase22:governance_no_state_write" "FAIL"
fi

# ─── Phase 23: packaging_and_contract_v4_smoke ───
echo "[phase 23] packaging_and_contract_v4_smoke"
if [ -f "$REPO_ROOT/pyproject.toml" ] && [ -f "$PLUGIN" ] && [ -d "$CASE1" ]; then
  P23_VENV="$REGRESSION_TMP/phase23_venv"
  P23_PROJ="$REGRESSION_TMP/phase23_proj"
  P23_WS="$REGRESSION_TMP/phase23_ws"
  P23_STATE="$REGRESSION_TMP/phase23_state"
  rm -rf "$P23_VENV" "$P23_PROJ" "$P23_WS" "$P23_STATE"
  mkdir -p "$P23_PROJ" "$P23_WS" "$P23_STATE"

  set +e
  "$PYTHON_BIN" -m venv "$P23_VENV" > /dev/null 2>&1
  P23_VENV_RC=$?
  if [ "$P23_VENV_RC" -eq 0 ]; then
    "$P23_VENV/bin/python3" -m pip install --upgrade pip setuptools wheel > /dev/null 2>&1
    P23_BOOTSTRAP_RC=$?
  else
    P23_BOOTSTRAP_RC=1
  fi
  if [ "$P23_VENV_RC" -eq 0 ] && [ "$P23_BOOTSTRAP_RC" -eq 0 ]; then
    "$P23_VENV/bin/python3" -m pip install -e "$REPO_ROOT" > /dev/null 2>&1
    P23_PIP_RC=$?
  else
    P23_PIP_RC=1
  fi
  set -e

  set +e
  P23_UNINST_ERR=$(PYTHONPATH="" "$PYTHON_BIN" -m hongzhi_ai_kit --help 2>&1 >/dev/null)
  P23_UNINST_RC=$?
  set -e
  if [ "$P23_UNINST_RC" -ne 0 ]; then
    echo "[phase 23] install hint: python3 -m pip install -U pip setuptools wheel && python3 -m pip install -e ."
    if echo "$P23_UNINST_ERR" | grep -q "No module named hongzhi_ai_kit"; then
      check "Phase23:uninstalled_install_hint" "PASS"
    else
      check "Phase23:uninstalled_install_hint" "FAIL"
    fi
  else
    echo "[phase 23] note: hongzhi_ai_kit already importable in base interpreter"
    check "Phase23:uninstalled_install_hint" "PASS"
  fi

  if [ "$P23_VENV_RC" -ne 0 ] || [ "$P23_BOOTSTRAP_RC" -ne 0 ] || [ "$P23_PIP_RC" -ne 0 ]; then
    check "Phase23:package_import_smoke" "FAIL"
    check "Phase23:console_entry_smoke" "FAIL"
    check "Phase23:governance_disabled_no_outputs" "FAIL"
    check "Phase23:capabilities_stdout_contract" "FAIL"
  else
    set +e
    HONGZHI_PLUGIN_ENABLE=1 "$P23_VENV/bin/python3" -m hongzhi_ai_kit status --repo-root "$P23_PROJ" > /dev/null 2>&1
    P23_MOD_RC=$?
    set -e
    if [ "$P23_MOD_RC" -eq 0 ]; then
      check "Phase23:package_import_smoke" "PASS"
    else
      check "Phase23:package_import_smoke" "FAIL"
    fi

    set +e
    HONGZHI_PLUGIN_ENABLE=1 "$P23_VENV/bin/hongzhi-ai-kit" status --repo-root "$P23_PROJ" > /dev/null 2>&1
    P23_CON_RC=$?
    set -e
    if [ "$P23_CON_RC" -eq 0 ]; then
      check "Phase23:console_entry_smoke" "PASS"
    else
      check "Phase23:console_entry_smoke" "FAIL"
    fi

    rm -rf "$P23_WS" "$P23_STATE"
    mkdir -p "$P23_WS" "$P23_STATE"
    set +e
    unset HONGZHI_PLUGIN_ENABLE 2>/dev/null || true
    "$P23_VENV/bin/python3" -m hongzhi_ai_kit discover \
      --repo-root "$CASE1" --workspace-root "$P23_WS" --global-state-root "$P23_STATE" > /dev/null 2>&1
    P23_BLOCK_RC=$?
    set -e
    P23_BLOCK_FILES=$(find "$P23_WS" "$P23_STATE" -type f \
      \( -name "capabilities.json" -o -name "capabilities.jsonl" -o -name "capability_index.json" -o -name "latest.json" -o -name "run_meta.json" \) | wc -l | tr -d ' ')
    if [ "$P23_BLOCK_RC" -eq 10 ] && [ "$P23_BLOCK_FILES" = "0" ]; then
      check "Phase23:governance_disabled_no_outputs" "PASS"
    else
      check "Phase23:governance_disabled_no_outputs" "FAIL"
    fi

    rm -rf "$P23_WS" "$P23_STATE"
    mkdir -p "$P23_WS" "$P23_STATE"
    set +e
    P23_OUT=$(HONGZHI_PLUGIN_ENABLE=1 "$P23_VENV/bin/python3" -m hongzhi_ai_kit discover \
      --repo-root "$CASE1" --workspace-root "$P23_WS" --global-state-root "$P23_STATE" 2>/dev/null)
    P23_DISC_RC=$?
    set -e
    P23_CAP_LINE=$(printf '%s\n' "$P23_OUT" | grep '^HONGZHI_CAPS ' || true)
    P23_CAP_PATH=$(extract_machine_path "$P23_CAP_LINE")
    if [ "$P23_DISC_RC" -eq 0 ] && [ -n "$P23_CAP_PATH" ] && [ -f "$P23_CAP_PATH" ]; then
      check "Phase23:capabilities_stdout_contract" "PASS"
    else
      check "Phase23:capabilities_stdout_contract" "FAIL"
    fi
  fi
else
  check "Phase23:uninstalled_install_hint" "FAIL"
  check "Phase23:package_import_smoke" "FAIL"
  check "Phase23:console_entry_smoke" "FAIL"
  check "Phase23:governance_disabled_no_outputs" "FAIL"
  check "Phase23:capabilities_stdout_contract" "FAIL"
fi

# ─── Phase 24: release_and_contract_v4_guard ───
echo "[phase 24] release_and_contract_v4_guard"
if [ -f "$REPO_ROOT/pyproject.toml" ] && [ -f "$PLUGIN" ] && [ -d "$CASE1" ]; then
  P24_DIST="$REGRESSION_TMP/phase24_dist"
  P24_BUILD_VENV="$REGRESSION_TMP/phase24_build_venv"
  P24_WHEEL_VENV="$REGRESSION_TMP/phase24_wheel_venv"
  P24_PROJ="$REGRESSION_TMP/phase24_proj"
  P24_WS="$REGRESSION_TMP/phase24_ws"
  P24_STATE="$REGRESSION_TMP/phase24_state"
  rm -rf "$P24_DIST" "$P24_BUILD_VENV" "$P24_WHEEL_VENV" "$P24_PROJ" "$P24_WS" "$P24_STATE"
  mkdir -p "$P24_DIST" "$P24_PROJ" "$P24_WS" "$P24_STATE"

  set +e
  "$PYTHON_BIN" -m venv "$P24_BUILD_VENV" > /dev/null 2>&1
  P24_BUILD_VENV_RC=$?
  if [ "$P24_BUILD_VENV_RC" -eq 0 ]; then
    "$P24_BUILD_VENV/bin/python3" -m pip install --upgrade pip setuptools wheel build > /dev/null 2>&1
    P24_BUILD_BOOT_RC=$?
  else
    P24_BUILD_BOOT_RC=1
  fi
  if [ "$P24_BUILD_VENV_RC" -eq 0 ] && [ "$P24_BUILD_BOOT_RC" -eq 0 ]; then
    "$P24_BUILD_VENV/bin/python3" -m build --wheel --sdist --outdir "$P24_DIST" "$REPO_ROOT" > /dev/null 2>&1
    P24_BUILD_RC=$?
  else
    P24_BUILD_RC=1
  fi
  set -e

  if [ "$P24_BUILD_RC" -eq 0 ] && ls "$P24_DIST"/*.tar.gz >/dev/null 2>&1; then
    check "Phase24:sdist_build_smoke" "PASS"
  else
    check "Phase24:sdist_build_smoke" "FAIL"
  fi

  if [ "$P24_BUILD_RC" -eq 0 ] && ls "$P24_DIST"/*.whl >/dev/null 2>&1; then
    set +e
    "$PYTHON_BIN" -m venv "$P24_WHEEL_VENV" > /dev/null 2>&1
    P24_WHEEL_VENV_RC=$?
    if [ "$P24_WHEEL_VENV_RC" -eq 0 ]; then
      PYTHONPATH="" "$P24_WHEEL_VENV/bin/python3" -m pip install --force-reinstall "$P24_DIST"/*.whl > /dev/null 2>&1
      P24_WHEEL_INSTALL_RC=$?
    else
      P24_WHEEL_INSTALL_RC=1
    fi
    if [ "$P24_WHEEL_INSTALL_RC" -eq 0 ]; then
      PYTHONPATH="" "$P24_WHEEL_VENV/bin/hongzhi-ai-kit" --help > /dev/null 2>&1
      P24_HELP_RC=$?
      PYTHONPATH="" "$P24_WHEEL_VENV/bin/python3" -m hongzhi_ai_kit --help > /dev/null 2>&1
      P24_MOD_HELP_RC=$?
    else
      P24_HELP_RC=1
      P24_MOD_HELP_RC=1
    fi
    set -e
    if [ "$P24_WHEEL_INSTALL_RC" -eq 0 ] && [ "$P24_HELP_RC" -eq 0 ] && [ "$P24_MOD_HELP_RC" -eq 0 ]; then
      check "Phase24:wheel_install_smoke" "PASS"
    else
      check "Phase24:wheel_install_smoke" "FAIL"
    fi
  else
    check "Phase24:wheel_install_smoke" "FAIL"
  fi

  set +e
  P24_TRACKED_JUNK=$(git -C "$REPO_ROOT" ls-files | grep -E '(^|/)\.DS_Store$|(^|/)__pycache__/|^prompt-dsl-system/tools/deliveries/|^prompt-dsl-system/tools/snapshots/' || true)
  set -e
  if [ -z "$P24_TRACKED_JUNK" ]; then
    check "Phase24:gitignore_guard" "PASS"
  else
    check "Phase24:gitignore_guard" "FAIL"
  fi

  if [ -d "$P24_WHEEL_VENV" ] && [ -x "$P24_WHEEL_VENV/bin/python3" ]; then
    set +e
    P24_STATUS_OUT=$(PYTHONPATH="" HONGZHI_PLUGIN_ENABLE=1 "$P24_WHEEL_VENV/bin/python3" -m hongzhi_ai_kit status --repo-root "$P24_PROJ" 2>/dev/null)
    P24_STATUS_RC=$?
    set -e
    if [ "$P24_STATUS_RC" -eq 0 ] && echo "$P24_STATUS_OUT" | grep -q "package_version=" && echo "$P24_STATUS_OUT" | grep -q "plugin_version=" && echo "$P24_STATUS_OUT" | grep -q "contract_version="; then
      check "Phase24:version_triple_present" "PASS"
    else
      check "Phase24:version_triple_present" "FAIL"
    fi

    rm -rf "$P24_WS" "$P24_STATE"
    mkdir -p "$P24_WS" "$P24_STATE"
    set +e
    unset HONGZHI_PLUGIN_ENABLE 2>/dev/null || true
    P24_GOV_OUT=$(PYTHONPATH="" "$P24_WHEEL_VENV/bin/python3" -m hongzhi_ai_kit discover \
      --repo-root "$CASE1" --workspace-root "$P24_WS" --global-state-root "$P24_STATE" 2>/dev/null)
    P24_GOV_RC=$?
    set -e
    P24_GOV_FILES=$(find "$P24_WS" "$P24_STATE" -type f \
      \( -name "capabilities.json" -o -name "capabilities.jsonl" -o -name "capability_index.json" -o -name "latest.json" -o -name "run_meta.json" \) | wc -l | tr -d ' ')
    if [ "$P24_GOV_RC" -eq 10 ] && [ "$P24_GOV_FILES" = "0" ] && \
       echo "$P24_GOV_OUT" | grep -q "^HONGZHI_GOV_BLOCK " && \
       echo "$P24_GOV_OUT" | grep -q "package_version=" && \
       echo "$P24_GOV_OUT" | grep -q "plugin_version=" && \
       echo "$P24_GOV_OUT" | grep -q "contract_version="; then
      check "Phase24:gov_block_has_versions_and_zero_write" "PASS"
    else
      check "Phase24:gov_block_has_versions_and_zero_write" "FAIL"
    fi
  else
    check "Phase24:version_triple_present" "FAIL"
    check "Phase24:gov_block_has_versions_and_zero_write" "FAIL"
  fi
else
  check "Phase24:version_triple_present" "FAIL"
  check "Phase24:wheel_install_smoke" "FAIL"
  check "Phase24:sdist_build_smoke" "FAIL"
  check "Phase24:gitignore_guard" "FAIL"
  check "Phase24:gov_block_has_versions_and_zero_write" "FAIL"
fi

# ─── Phase 25: governance_v3_limits_pipeline ───
echo "[phase 25] governance_v3_limits_pipeline"
PIPE_PLUGIN_DISCOVER="$REPO_ROOT/prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_plugin_discover.md"
if [ -f "$PLUGIN" ] && [ -d "$CASE1" ]; then
  P25_TMP="$REGRESSION_TMP/phase25"
  P25_WS="$REGRESSION_TMP/phase25_ws"
  P25_STATE="$REGRESSION_TMP/phase25_state"
  rm -rf "$P25_TMP" "$P25_WS" "$P25_STATE"
  mkdir -p "$P25_TMP/allowed_repo" "$P25_TMP/denied_repo" "$P25_TMP/blocked_repo" "$P25_WS" "$P25_STATE"
  ln -s "$P25_TMP/denied_repo" "$P25_TMP/denied_link"
  cat > "$P25_TMP/policy.yaml" <<EOF
plugin:
  enabled: true
  allow_roots: ["$P25_TMP/allowed_repo"]
  deny_roots: ["$P25_TMP/denied_repo"]
EOF

  # token_ttl_expired_block
  P25_TOKEN_EXPIRED='{"token":"T-EXPIRED","issued_at":"2000-01-01T00:00:00Z","ttl_seconds":60,"scope":["status","discover"]}'
  set +e
  "$PYTHON_BIN" "$PLUGIN" status --repo-root "$P25_TMP/blocked_repo" --kit-root "$P25_TMP" --permit-token "$P25_TOKEN_EXPIRED" > /dev/null 2>&1
  P25_TTL_RC=$?
  set -e
  if [ "$P25_TTL_RC" -eq 12 ]; then
    check "Phase25:token_ttl_expired_block" "PASS"
  else
    check "Phase25:token_ttl_expired_block" "FAIL"
  fi

  # token_scope_block
  P25_TOKEN_SCOPE='{"token":"T-SCOPE","scope":["discover"],"expires_at":"2999-01-01T00:00:00Z"}'
  set +e
  "$PYTHON_BIN" "$PLUGIN" status --repo-root "$P25_TMP/blocked_repo" --kit-root "$P25_TMP" --permit-token "$P25_TOKEN_SCOPE" > /dev/null 2>&1
  P25_SCOPE_RC=$?
  set -e
  if [ "$P25_SCOPE_RC" -eq 12 ]; then
    check "Phase25:token_scope_block" "PASS"
  else
    check "Phase25:token_scope_block" "FAIL"
  fi

  # symlink_bypass_denied
  set +e
  "$PYTHON_BIN" "$PLUGIN" status --repo-root "$P25_TMP/denied_link" --kit-root "$P25_TMP" > /dev/null 2>&1
  P25_LINK_RC=$?
  set -e
  if [ "$P25_LINK_RC" -eq 11 ]; then
    check "Phase25:symlink_bypass_denied" "PASS"
  else
    check "Phase25:symlink_bypass_denied" "FAIL"
  fi

  # limits_hit_normal_warn
  set +e
  P25_OUT_NORMAL=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --workspace-root "$P25_WS" --global-state-root "$P25_STATE" \
    --max-files 1 2>/dev/null)
  P25_NORMAL_RC=$?
  set -e
  if [ "$P25_NORMAL_RC" -eq 0 ] && echo "$P25_OUT_NORMAL" | grep -q "limits_hit=1"; then
    check "Phase25:limits_hit_normal_warn" "PASS"
  else
    check "Phase25:limits_hit_normal_warn" "FAIL"
  fi

  # limits_hit_strict_fail
  set +e
  P25_OUT_STRICT=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --workspace-root "$P25_WS" --global-state-root "$P25_STATE" \
    --max-files 1 --strict 2>/dev/null)
  P25_STRICT_RC=$?
  set -e
  if [ "$P25_STRICT_RC" -eq 20 ] && echo "$P25_OUT_STRICT" | grep -q "limits_hit=1"; then
    check "Phase25:limits_hit_strict_fail" "PASS"
  else
    check "Phase25:limits_hit_strict_fail" "FAIL"
  fi

  # capability_index_gated_by_governance
  rm -rf "$P25_WS" "$P25_STATE"
  mkdir -p "$P25_WS" "$P25_STATE"
  set +e
  unset HONGZHI_PLUGIN_ENABLE 2>/dev/null || true
  "$PYTHON_BIN" "$PLUGIN" discover --repo-root "$CASE1" --workspace-root "$P25_WS" --global-state-root "$P25_STATE" > /dev/null 2>&1
  P25_GOV_RC=$?
  set -e
  if [ "$P25_GOV_RC" -eq 10 ] && [ ! -f "$P25_STATE/capability_index.json" ]; then
    check "Phase25:capability_index_gated_by_governance" "PASS"
  else
    check "Phase25:capability_index_gated_by_governance" "FAIL"
  fi

  # pipeline_status_decide_discover_smoke
  if [ -f "$PIPE_PLUGIN_DISCOVER" ] && \
     grep -q "Step 1 — Status" "$PIPE_PLUGIN_DISCOVER" && \
     grep -q "Step 2 — Decide" "$PIPE_PLUGIN_DISCOVER" && \
     grep -q "Step 3 — Discover" "$PIPE_PLUGIN_DISCOVER" && \
     grep -q "skill_governance_plugin_status" "$PIPE_PLUGIN_DISCOVER"; then
    check "Phase25:pipeline_status_decide_discover_smoke" "PASS"
  else
    check "Phase25:pipeline_status_decide_discover_smoke" "FAIL"
  fi
else
  check "Phase25:token_ttl_expired_block" "FAIL"
  check "Phase25:token_scope_block" "FAIL"
  check "Phase25:symlink_bypass_denied" "FAIL"
  check "Phase25:limits_hit_normal_warn" "FAIL"
  check "Phase25:limits_hit_strict_fail" "FAIL"
  check "Phase25:capability_index_gated_by_governance" "FAIL"
  check "Phase25:pipeline_status_decide_discover_smoke" "FAIL"
fi

# ─── Phase 26: calibration_layer_round20 ───
echo "[phase 26] calibration_layer_round20"
if [ -f "$PLUGIN" ] && [ -d "$CASE4" ] && [ -d "$CASE5" ]; then
  P26_WS="$REGRESSION_TMP/phase26_ws"
  P26_STATE="$REGRESSION_TMP/phase26_state"
  rm -rf "$P26_WS" "$P26_STATE"
  mkdir -p "$P26_WS" "$P26_STATE"

  # calibration_low_confidence_exit21_strict (case4 + case5)
  set +e
  P26_OUT_S4=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE4" --workspace-root "$P26_WS" --global-state-root "$P26_STATE" \
    --strict 2>/dev/null)
  P26_RC_S4=$?
  P26_OUT_S5=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE5" --workspace-root "$P26_WS" --global-state-root "$P26_STATE" \
    --strict 2>/dev/null)
  P26_RC_S5=$?
  set -e
  if [ "$P26_RC_S4" -eq 21 ] && [ "$P26_RC_S5" -eq 21 ] && \
     echo "$P26_OUT_S4" | grep -q "needs_human_hint=1" && \
     echo "$P26_OUT_S5" | grep -q "needs_human_hint=1"; then
    check "Phase26:calibration_low_confidence_exit21_strict" "PASS"
  else
    check "Phase26:calibration_low_confidence_exit21_strict" "FAIL"
  fi

  # calibration_non_strict_warn_exit0 (case4)
  set +e
  P26_OUT_NS=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE4" --workspace-root "$P26_WS" --global-state-root "$P26_STATE" 2>/dev/null)
  P26_RC_NS=$?
  set -e
  if [ "$P26_RC_NS" -eq 0 ] && echo "$P26_OUT_NS" | grep -q "needs_human_hint=1"; then
    check "Phase26:calibration_non_strict_warn_exit0" "PASS"
  else
    check "Phase26:calibration_non_strict_warn_exit0" "FAIL"
  fi

  # calibration outputs exist
  P26_CHECK3=$("$PYTHON_BIN" - <<PY
import pathlib
ws = pathlib.Path("$P26_WS")
caps = sorted(ws.rglob("capabilities.json"))
if not caps:
    print("0")
    raise SystemExit(0)
latest = caps[-1].parent
ok = (latest / "calibration" / "calibration_report.json").is_file() and \
     (latest / "calibration" / "hints_suggested.yaml").is_file()
print("1" if ok else "0")
PY
)
  if [ "$P26_CHECK3" = "1" ]; then
    check "Phase26:calibration_outputs_exist_in_workspace" "PASS"
  else
    check "Phase26:calibration_outputs_exist_in_workspace" "FAIL"
  fi

  # capabilities contains calibration fields
  P26_CAP_LINE=$(printf '%s\n' "$P26_OUT_NS" | grep '^HONGZHI_CAPS ' || true)
  P26_CAP_PATH=$(extract_machine_path "$P26_CAP_LINE")
  P26_CHECK4=$("$PYTHON_BIN" - <<PY
import json, pathlib
cap = pathlib.Path("$P26_CAP_PATH")
ok = False
if cap.is_file():
    data = json.loads(cap.read_text(encoding="utf-8"))
    cal = data.get("calibration", {})
    ok = isinstance(cal.get("needs_human_hint"), bool) and bool(cal.get("confidence_tier"))
print("1" if ok else "0")
PY
)
  if [ "$P26_CHECK4" = "1" ]; then
    check "Phase26:capabilities_contains_calibration_fields" "PASS"
  else
    check "Phase26:capabilities_contains_calibration_fields" "FAIL"
  fi
else
  check "Phase26:calibration_low_confidence_exit21_strict" "FAIL"
  check "Phase26:calibration_non_strict_warn_exit0" "FAIL"
  check "Phase26:calibration_outputs_exist_in_workspace" "FAIL"
  check "Phase26:capabilities_contains_calibration_fields" "FAIL"
fi

# ─── Phase 27: hint_loop_layout_adapters_round21 ───
echo "[phase 27] hint_loop_layout_adapters_round21"
if [ -f "$PLUGIN" ] && [ -d "$CASE1" ] && [ -d "$CASE5" ] && [ -d "$CASE6" ] && [ -d "$CASE7" ]; then
  P27_WS="$REGRESSION_TMP/phase27_ws"
  P27_STATE="$REGRESSION_TMP/phase27_state"
  rm -rf "$P27_WS" "$P27_STATE"
  mkdir -p "$P27_WS" "$P27_STATE"

  # hint_loop_strict_fail_then_apply_pass
  set +e
  P27_OUT_FAIL=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE5" --workspace-root "$P27_WS" --global-state-root "$P27_STATE" \
    --strict 2>/dev/null)
  P27_RC_FAIL=$?
  set -e
  P27_HINT_LINE=$(printf '%s\n' "$P27_OUT_FAIL" | grep '^HONGZHI_HINTS ' || true)
  P27_HINT_PATH=$(extract_machine_path "$P27_HINT_LINE")
  set +e
  P27_OUT_APPLY=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE5" --workspace-root "$P27_WS" --global-state-root "$P27_STATE" \
    --strict --apply-hints "$P27_HINT_PATH" --hint-strategy aggressive 2>/dev/null)
  P27_RC_APPLY=$?
  set -e
  if [ "$P27_RC_FAIL" -eq 21 ] && [ -n "$P27_HINT_PATH" ] && [ -f "$P27_HINT_PATH" ] && \
     [ "$P27_RC_APPLY" -eq 0 ] && echo "$P27_OUT_APPLY" | grep -q "hint_applied=1"; then
    check "Phase27:hint_loop_strict_fail_then_apply_pass" "PASS"
  else
    check "Phase27:hint_loop_strict_fail_then_apply_pass" "FAIL"
  fi

  # adapter_maven_multi_module_smoke
  set +e
  P27_OUT_MAVEN=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE6" --workspace-root "$P27_WS" --global-state-root "$P27_STATE" \
    --keywords "notice,billing" 2>/dev/null)
  P27_RC_MAVEN=$?
  set -e
  P27_MAVEN_CAP=$(extract_machine_path "$(printf '%s\n' "$P27_OUT_MAVEN" | grep '^HONGZHI_CAPS ' | head -n 1 || true)")
  P27_MAVEN_OK=$("$PYTHON_BIN" - <<PY
import json, pathlib
cap = pathlib.Path("$P27_MAVEN_CAP")
ok = False
if cap.is_file():
    data = json.loads(cap.read_text(encoding="utf-8"))
    details = data.get("layout_details", {})
    ok = (data.get("layout") == "multi-module-maven") and bool(details.get("adapter_used"))
print("1" if ok else "0")
PY
)
  if [ "$P27_RC_MAVEN" -eq 0 ] && [ "$P27_MAVEN_OK" = "1" ]; then
    check "Phase27:adapter_maven_multi_module_smoke" "PASS"
  else
    check "Phase27:adapter_maven_multi_module_smoke" "FAIL"
  fi

  # adapter_nonstandard_java_root_smoke
  set +e
  P27_OUT_NONSTD=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE7" --workspace-root "$P27_WS" --global-state-root "$P27_STATE" \
    --keywords "asset" 2>/dev/null)
  P27_RC_NONSTD=$?
  set -e
  P27_NONSTD_CAP=$(extract_machine_path "$(printf '%s\n' "$P27_OUT_NONSTD" | grep '^HONGZHI_CAPS ' | head -n 1 || true)")
  P27_NONSTD_OK=$("$PYTHON_BIN" - <<PY
import json, pathlib
cap = pathlib.Path("$P27_NONSTD_CAP")
ok = False
if cap.is_file():
    data = json.loads(cap.read_text(encoding="utf-8"))
    ok = (data.get("layout") == "nonstandard-java-root")
print("1" if ok else "0")
PY
)
  if [ "$P27_RC_NONSTD" -eq 0 ] && [ "$P27_NONSTD_OK" = "1" ]; then
    check "Phase27:adapter_nonstandard_java_root_smoke" "PASS"
  else
    check "Phase27:adapter_nonstandard_java_root_smoke" "FAIL"
  fi

  # reuse_validated_smoke
  set +e
  HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --workspace-root "$P27_WS" --global-state-root "$P27_STATE" > /dev/null 2>&1
  P27_OUT_REUSE=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --workspace-root "$P27_WS" --global-state-root "$P27_STATE" \
    --smart --smart-max-age-seconds 9999 2>/dev/null)
  P27_RC_REUSE=$?
  set -e
  P27_REUSE_CAP=$(extract_machine_path "$(printf '%s\n' "$P27_OUT_REUSE" | grep '^HONGZHI_CAPS ' | head -n 1 || true)")
  P27_REUSE_OK=$("$PYTHON_BIN" - <<PY
import json, pathlib
cap = pathlib.Path("$P27_REUSE_CAP")
ok = False
if cap.is_file():
    data = json.loads(cap.read_text(encoding="utf-8"))
    smart = data.get("smart", {})
    ok = bool(smart.get("reused")) and bool(smart.get("reuse_validated"))
print("1" if ok else "0")
PY
)
  if [ "$P27_RC_REUSE" -eq 0 ] && echo "$P27_OUT_REUSE" | grep -q "reuse_validated=1" && \
     echo "$P27_OUT_REUSE" | grep -q "smart_reused=1" && [ "$P27_REUSE_OK" = "1" ]; then
    check "Phase27:reuse_validated_smoke" "PASS"
  else
    check "Phase27:reuse_validated_smoke" "FAIL"
  fi

  # governance_disabled_zero_write
  P27_WS_GOV="$REGRESSION_TMP/phase27_ws_gov"
  P27_STATE_GOV="$REGRESSION_TMP/phase27_state_gov"
  rm -rf "$P27_WS_GOV" "$P27_STATE_GOV"
  mkdir -p "$P27_WS_GOV" "$P27_STATE_GOV"
  set +e
  unset HONGZHI_PLUGIN_ENABLE 2>/dev/null || true
  "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --workspace-root "$P27_WS_GOV" --global-state-root "$P27_STATE_GOV" > /dev/null 2>&1
  P27_GOV_RC=$?
  set -e
  P27_GOV_FILES=$(find "$P27_WS_GOV" "$P27_STATE_GOV" -type f \
    \( -name "capabilities.json" -o -name "capabilities.jsonl" -o -name "capability_index.json" -o -name "latest.json" -o -name "run_meta.json" -o -name "hints.json" \) | wc -l | tr -d ' ')
  if [ "$P27_GOV_RC" -eq 10 ] && [ "$P27_GOV_FILES" = "0" ]; then
    check "Phase27:governance_disabled_zero_write" "PASS"
  else
    check "Phase27:governance_disabled_zero_write" "FAIL"
  fi

  # capability_index_records_hint_runs
  P27_HINT_RUNS_OK=$("$PYTHON_BIN" - <<PY
import json, pathlib, sys
state = pathlib.Path("$P27_STATE")
plugin_path = pathlib.Path("$PLUGIN")
repo = pathlib.Path("$CASE5").resolve()
sys.path.insert(0, str(pathlib.Path("$REPO_ROOT/prompt-dsl-system/tools")))
import importlib.util
spec = importlib.util.spec_from_file_location("hongzhi_plugin", str(plugin_path))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
fp = mod.compute_project_fingerprint(repo)
idx = state / "capability_index.json"
ok = False
if idx.is_file():
    data = json.loads(idx.read_text(encoding="utf-8"))
    entry = data.get("projects", {}).get(fp, {})
    if isinstance(entry, dict):
        latest = entry.get("latest", {})
        runs = entry.get("runs", [])
        latest_hit = bool((latest.get("metrics") or {}).get("hint_applied", False))
        run_hit = any(bool((r.get("metrics") or {}).get("hint_applied", False)) for r in runs if isinstance(r, dict))
        ok = latest_hit or run_hit
print("1" if ok else "0")
PY
)
  if [ "$P27_HINT_RUNS_OK" = "1" ]; then
    check "Phase27:capability_index_records_hint_runs" "PASS"
  else
    check "Phase27:capability_index_records_hint_runs" "FAIL"
  fi
else
  check "Phase27:hint_loop_strict_fail_then_apply_pass" "FAIL"
  check "Phase27:adapter_maven_multi_module_smoke" "FAIL"
  check "Phase27:adapter_nonstandard_java_root_smoke" "FAIL"
  check "Phase27:reuse_validated_smoke" "FAIL"
  check "Phase27:governance_disabled_zero_write" "FAIL"
  check "Phase27:capability_index_records_hint_runs" "FAIL"
fi

# ─── Phase 28: hint_assetization_profile_delta_bundle_round22 ───
echo "[phase 28] hint_assetization_profile_delta_bundle_round22"
if [ -f "$PLUGIN" ] && [ -d "$CASE5" ]; then
  P28_WS="$REGRESSION_TMP/phase28_ws"
  P28_STATE="$REGRESSION_TMP/phase28_state"
  rm -rf "$P28_WS" "$P28_STATE"
  mkdir -p "$P28_WS" "$P28_STATE"

  # a) strict -> exit21 -> HONGZHI_HINTS present + bundle exists + schema ok
  set +e
  P28_OUT_A=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE5" --workspace-root "$P28_WS" --global-state-root "$P28_STATE" \
    --strict 2>/dev/null)
  P28_RC_A=$?
  set -e
  P28_HINT_LINE=$(printf '%s\n' "$P28_OUT_A" | grep '^HONGZHI_HINTS ' || true)
  P28_HINT_PATH=$(extract_machine_path "$P28_HINT_LINE")
  P28_CHECK_A=$("$PYTHON_BIN" - <<PY
import json, pathlib
p = pathlib.Path("$P28_HINT_PATH")
ok = False
if p.is_file():
    data = json.loads(p.read_text(encoding="utf-8"))
    ok = (
        data.get("kind") == "profile_delta" and
        bool(data.get("created_at")) and
        isinstance(data.get("delta", {}).get("identity", {}), dict)
    )
print("1" if ok else "0")
PY
)
  if [ "$P28_RC_A" -eq 21 ] && [ -n "$P28_HINT_PATH" ] && [ "$P28_CHECK_A" = "1" ]; then
    check "Phase28:strict_exit21_hints_bundle_schema" "PASS"
  else
    check "Phase28:strict_exit21_hints_bundle_schema" "FAIL"
  fi

  # b) apply-hints -> exit0 + hint_applied=1 + hint_verified=1
  set +e
  P28_OUT_B=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE5" --workspace-root "$P28_WS" --global-state-root "$P28_STATE" \
    --strict --apply-hints "$P28_HINT_PATH" --hint-strategy aggressive 2>/dev/null)
  P28_RC_B=$?
  set -e
  if [ "$P28_RC_B" -eq 0 ] && \
     echo "$P28_OUT_B" | grep -q "hint_applied=1" && \
     echo "$P28_OUT_B" | grep -q "hint_verified=1"; then
    check "Phase28:apply_hints_verified_pass" "PASS"
  else
    check "Phase28:apply_hints_verified_pass" "FAIL"
  fi

  # c) expired bundle -> strict exit22 + hint_expired=1
  P28_EXPIRED="$P28_WS/expired_hint_bundle.json"
  "$PYTHON_BIN" - <<PY
import json, pathlib
src = pathlib.Path("$P28_HINT_PATH")
dst = pathlib.Path("$P28_EXPIRED")
data = json.loads(src.read_text(encoding="utf-8")) if src.is_file() else {}
data["created_at"] = "2000-01-01T00:00:00Z"
data["expires_at"] = "2000-01-01T00:00:01Z"
data["ttl_seconds"] = 1
dst.parent.mkdir(parents=True, exist_ok=True)
dst.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\\n", encoding="utf-8")
PY
  set +e
  P28_OUT_C=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE5" --workspace-root "$P28_WS" --global-state-root "$P28_STATE" \
    --strict --apply-hints "$P28_EXPIRED" 2>/dev/null)
  P28_RC_C=$?
  set -e
  if [ "$P28_RC_C" -eq 22 ] && echo "$P28_OUT_C" | grep -q "hint_expired=1"; then
    check "Phase28:expired_bundle_strict_exit22" "PASS"
  else
    check "Phase28:expired_bundle_strict_exit22" "FAIL"
  fi

  # d) governance disabled -> exit10 and no hint bundle file created (0 writes)
  P28_WS_D="$REGRESSION_TMP/phase28_ws_disabled"
  P28_STATE_D="$REGRESSION_TMP/phase28_state_disabled"
  rm -rf "$P28_WS_D" "$P28_STATE_D"
  mkdir -p "$P28_WS_D" "$P28_STATE_D"
  set +e
  unset HONGZHI_PLUGIN_ENABLE 2>/dev/null || true
  "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE5" --workspace-root "$P28_WS_D" --global-state-root "$P28_STATE_D" --strict > /dev/null 2>&1
  P28_RC_D=$?
  set -e
  P28_WRITES_D=$(find "$P28_WS_D" "$P28_STATE_D" -type f \
    \( -name "hints.json" -o -name "capabilities.json" -o -name "capabilities.jsonl" -o -name "capability_index.json" -o -name "latest.json" -o -name "run_meta.json" \) | wc -l | tr -d ' ')
  if [ "$P28_RC_D" -eq 10 ] && [ "$P28_WRITES_D" = "0" ]; then
    check "Phase28:governance_disabled_zero_write" "PASS"
  else
    check "Phase28:governance_disabled_zero_write" "FAIL"
  fi

  # e) token missing hint_bundle scope -> no bundle, strict exit23, HONGZHI_HINTS_BLOCK present
  P28_POLICY="$REGRESSION_TMP/phase28_policy"
  mkdir -p "$P28_POLICY/allow_only"
  cat > "$P28_POLICY/policy.yaml" <<EOF
plugin:
  enabled: true
  allow_roots: ["$P28_POLICY/allow_only"]
  deny_roots: []
EOF
  P28_TOKEN_DISC='{"token":"T-DISC","scope":["discover"],"expires_at":"2999-01-01T00:00:00Z"}'
  set +e
  P28_OUT_E=$("$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE5" --workspace-root "$P28_WS" --global-state-root "$P28_STATE" \
    --kit-root "$P28_POLICY" --permit-token "$P28_TOKEN_DISC" --strict 2>/dev/null)
  P28_RC_E=$?
  set -e
  P28_HINT_E=$(extract_machine_path "$(printf '%s\n' "$P28_OUT_E" | grep '^HONGZHI_HINTS ' | head -n 1 || true)")
  if [ "$P28_RC_E" -eq 23 ] && echo "$P28_OUT_E" | grep -q "^HONGZHI_HINTS_BLOCK " && [ -z "$P28_HINT_E" ]; then
    check "Phase28:token_scope_missing_hint_bundle_block" "PASS"
  else
    check "Phase28:token_scope_missing_hint_bundle_block" "FAIL"
  fi

  # f) capability_index gated by governance disable (no update even when hints requested)
  P28_STATE_F="$REGRESSION_TMP/phase28_state_index_gate"
  mkdir -p "$P28_STATE_F"
  cat > "$P28_STATE_F/capability_index.json" <<'EOF'
{"version":"1.0.0","updated_at":"2000-01-01T00:00:00Z","projects":{}}
EOF
  BEFORE_F=$("$PYTHON_BIN" - <<PY
import pathlib
p = pathlib.Path("$P28_STATE_F/capability_index.json")
print(int(p.stat().st_mtime_ns))
PY
)
  set +e
  unset HONGZHI_PLUGIN_ENABLE 2>/dev/null || true
  "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE5" --workspace-root "$P28_WS_D" --global-state-root "$P28_STATE_F" --strict > /dev/null 2>&1
  P28_RC_F=$?
  set -e
  AFTER_F=$("$PYTHON_BIN" - <<PY
import pathlib
p = pathlib.Path("$P28_STATE_F/capability_index.json")
print(int(p.stat().st_mtime_ns))
PY
)
  if [ "$P28_RC_F" -eq 10 ] && [ "$BEFORE_F" = "$AFTER_F" ]; then
    check "Phase28:capability_index_gated_when_governance_denied" "PASS"
  else
    check "Phase28:capability_index_gated_when_governance_denied" "FAIL"
  fi
else
  check "Phase28:strict_exit21_hints_bundle_schema" "FAIL"
  check "Phase28:apply_hints_verified_pass" "FAIL"
  check "Phase28:expired_bundle_strict_exit22" "FAIL"
  check "Phase28:governance_disabled_zero_write" "FAIL"
  check "Phase28:token_scope_missing_hint_bundle_block" "FAIL"
  check "Phase28:capability_index_gated_when_governance_denied" "FAIL"
fi


# ─── Phase 29: capability_index_federation_round23 ───
echo "[phase 29] capability_index_federation_round23"
if [ -f "$PLUGIN" ] && [ -d "$CASE1" ]; then
  P29_WS="$REGRESSION_TMP/phase29_ws"
  P29_STATE="$REGRESSION_TMP/phase29_state"
  rm -rf "$P29_WS" "$P29_STATE"
  mkdir -p "$P29_WS" "$P29_STATE"

  # 1) federated_index write smoke + HONGZHI_INDEX pointer
  set +e
  P29_OUT_A=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --workspace-root "$P29_WS" --global-state-root "$P29_STATE" \
    --keywords "notice" 2>/dev/null)
  P29_RC_A=$?
  set -e
  P29_INDEX_LINE=$(printf '%s\n' "$P29_OUT_A" | grep '^HONGZHI_INDEX ' || true)
  P29_INDEX_PATH=$(extract_machine_path "$P29_INDEX_LINE")
  P29_FED_OK=$("$PYTHON_BIN" - <<PY
import json, pathlib
idx = pathlib.Path("$P29_INDEX_PATH")
ok = False
if idx.is_file():
    data = json.loads(idx.read_text(encoding="utf-8"))
    repos = data.get("repos", {})
    if isinstance(repos, dict) and repos:
        entry = next(iter(repos.values()))
        if isinstance(entry, dict):
            latest = entry.get("latest", {})
            runs = entry.get("runs", [])
            ok = bool(latest.get("run_id")) and isinstance(runs, list) and len(runs) >= 1
print("1" if ok else "0")
PY
)
  if [ "$P29_RC_A" -eq 0 ] && [ -n "$P29_INDEX_PATH" ] && [ "$P29_FED_OK" = "1" ]; then
    check "Phase29:federated_index_smoke" "PASS"
  else
    check "Phase29:federated_index_smoke" "FAIL"
  fi

  # 2) index list smoke
  set +e
  P29_OUT_LIST=$("$PYTHON_BIN" "$PLUGIN" index list --global-state-root "$P29_STATE" --top-k 5 2>/dev/null)
  P29_RC_LIST=$?
  set -e
  if [ "$P29_RC_LIST" -eq 0 ] && echo "$P29_OUT_LIST" | grep -q "repo_fp="; then
    check "Phase29:index_list_smoke" "PASS"
  else
    check "Phase29:index_list_smoke" "FAIL"
  fi

  # 3/4) query ranking + strict limits_hit filter
  P29_STATE_RANK="$REGRESSION_TMP/phase29_state_rank"
  rm -rf "$P29_STATE_RANK"
  mkdir -p "$P29_STATE_RANK"
  "$PYTHON_BIN" - <<PY
import json, pathlib
state = pathlib.Path("$P29_STATE_RANK")
idx = state / "federated_index.json"
data = {
    "version": "1.0.0",
    "updated_at": "2026-02-11T00:00:00Z",
    "repos": {
        "fp_hit_old": {
            "repo_fp": "fp_hit_old",
            "repo_root": "/tmp/fp_hit_old",
            "last_seen_at": "2026-02-11T00:00:00Z",
            "latest": {"run_id": "run_hit", "timestamp": "2026-02-11T00:00:00Z", "command": "discover"},
            "runs": [
                {
                    "run_id": "run_hit",
                    "timestamp": "2026-02-11T00:00:00Z",
                    "command": "discover",
                    "layout": "single-module-maven",
                    "metrics": {
                        "limits_hit": True,
                        "ambiguity_ratio": 0.10,
                        "confidence_tier": "high",
                        "keywords": ["notice"],
                        "endpoint_paths": ["/notice/list"],
                    },
                }
            ],
        },
        "fp_hit_new": {
            "repo_fp": "fp_hit_new",
            "repo_root": "/tmp/fp_hit_new",
            "last_seen_at": "2026-02-12T00:00:00Z",
            "latest": {"run_id": "run_clean", "timestamp": "2026-02-12T00:00:00Z", "command": "discover"},
            "runs": [
                {
                    "run_id": "run_clean",
                    "timestamp": "2026-02-12T00:00:00Z",
                    "command": "discover",
                    "layout": "single-module-maven",
                    "metrics": {
                        "limits_hit": False,
                        "ambiguity_ratio": 0.20,
                        "confidence_tier": "medium",
                        "keywords": ["notice"],
                        "endpoint_paths": ["/notice/list"],
                    },
                }
            ],
        },
    },
}
idx.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY
  set +e
  P29_OUT_Q_STRICT=$("$PYTHON_BIN" "$PLUGIN" index query \
    --global-state-root "$P29_STATE_RANK" --endpoint "/notice" --strict --top-k 2 2>/dev/null)
  P29_RC_Q_STRICT=$?
  P29_OUT_Q_INCLUDE=$("$PYTHON_BIN" "$PLUGIN" index query \
    --global-state-root "$P29_STATE_RANK" --endpoint "/notice" --strict --include-limits-hit --top-k 2 2>/dev/null)
  P29_RC_Q_INCLUDE=$?
  set -e
  P29_Q1=$(printf '%s\n' "$P29_OUT_Q_STRICT" | grep '^repo_fp=' | head -n 1 || true)
  P29_Q2=$(printf '%s\n' "$P29_OUT_Q_INCLUDE" | grep '^repo_fp=' | head -n 1 || true)
  if [ "$P29_RC_Q_STRICT" -eq 0 ] && echo "$P29_Q1" | grep -q "repo_fp=fp_hit_new"; then
    check "Phase29:index_query_strict_filters_limits_hit" "PASS"
  else
    check "Phase29:index_query_strict_filters_limits_hit" "FAIL"
  fi
  if [ "$P29_RC_Q_INCLUDE" -eq 0 ] && echo "$P29_Q2" | grep -q "repo_fp=fp_hit_new\\|repo_fp=fp_hit_old"; then
    # include-limits-hit should allow the limits_hit run to appear in ranked output
    if echo "$P29_OUT_Q_INCLUDE" | grep -q "repo_fp=fp_hit_old"; then
      check "Phase29:index_query_include_limits_hit" "PASS"
    else
      check "Phase29:index_query_include_limits_hit" "FAIL"
    fi
  else
    check "Phase29:index_query_include_limits_hit" "FAIL"
  fi

  # 5) index explain smoke
  P29_REPO_FP=$("$PYTHON_BIN" - <<PY
import json, pathlib
idx = pathlib.Path("$P29_STATE/federated_index.json")
fp = ""
if idx.is_file():
    data = json.loads(idx.read_text(encoding="utf-8"))
    repos = data.get("repos", {})
    if isinstance(repos, dict) and repos:
        fp = next(iter(repos.keys()))
print(fp)
PY
)
  P29_RUN_ID=$("$PYTHON_BIN" - <<PY
import json, pathlib
idx = pathlib.Path("$P29_STATE/federated_index.json")
run_id = ""
if idx.is_file():
    data = json.loads(idx.read_text(encoding="utf-8"))
    repos = data.get("repos", {})
    if isinstance(repos, dict) and repos:
        fp = next(iter(repos.keys()))
        entry = repos.get(fp, {})
        latest = entry.get("latest", {}) if isinstance(entry, dict) else {}
        run_id = str(latest.get("run_id", ""))
print(run_id)
PY
)
  set +e
  P29_OUT_EXPLAIN=$("$PYTHON_BIN" "$PLUGIN" index explain "$P29_REPO_FP" "$P29_RUN_ID" --global-state-root "$P29_STATE" 2>/dev/null)
  P29_RC_EXPLAIN=$?
  set -e
  P29_EXPLAIN_JSON="$REGRESSION_TMP/phase29_explain.json"
  printf '%s\n' "$P29_OUT_EXPLAIN" > "$P29_EXPLAIN_JSON"
  P29_EXPLAIN_OK=$("$PYTHON_BIN" - <<PY
import json, pathlib
ok = False
try:
    text = pathlib.Path("$P29_EXPLAIN_JSON").read_text(encoding="utf-8")
    start = text.find("{")
    if start >= 0:
        data = json.loads(text[start:])
    else:
        data = {}
    ok = (data.get("repo_fp") == "$P29_REPO_FP") and (data.get("run", {}).get("run_id") == "$P29_RUN_ID")
except Exception:
    ok = False
print("1" if ok else "0")
PY
)
  if [ "$P29_RC_EXPLAIN" -eq 0 ] && [ "$P29_EXPLAIN_OK" = "1" ]; then
    check "Phase29:index_explain_smoke" "PASS"
  else
    check "Phase29:index_explain_smoke" "FAIL"
  fi

  # 6) token scope missing federated_index -> strict exit24 + HONGZHI_INDEX_BLOCK + no federated write
  P29_WS_S="$REGRESSION_TMP/phase29_ws_scope_strict"
  P29_STATE_S="$REGRESSION_TMP/phase29_state_scope_strict"
  rm -rf "$P29_WS_S" "$P29_STATE_S"
  mkdir -p "$P29_WS_S" "$P29_STATE_S"
  P29_TOKEN_DISC='{"token":"T-DISC","scope":["discover"],"expires_at":"2999-01-01T00:00:00Z"}'
  set +e
  P29_OUT_S=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --workspace-root "$P29_WS_S" --global-state-root "$P29_STATE_S" \
    --permit-token "$P29_TOKEN_DISC" --strict 2>/dev/null)
  P29_RC_S=$?
  set -e
  if [ "$P29_RC_S" -eq 24 ] && echo "$P29_OUT_S" | grep -q "^HONGZHI_INDEX_BLOCK " && \
     echo "$P29_OUT_S" | grep -q "scope=federated_index" && [ ! -f "$P29_STATE_S/federated_index.json" ]; then
    check "Phase29:token_scope_missing_federated_index_strict_exit24" "PASS"
  else
    check "Phase29:token_scope_missing_federated_index_strict_exit24" "FAIL"
  fi

  # 7) token scope missing federated_index -> non-strict warn + exit0 + no federated write
  P29_WS_N="$REGRESSION_TMP/phase29_ws_scope_non_strict"
  P29_STATE_N="$REGRESSION_TMP/phase29_state_scope_non_strict"
  rm -rf "$P29_WS_N" "$P29_STATE_N"
  mkdir -p "$P29_WS_N" "$P29_STATE_N"
  set +e
  P29_OUT_N=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --workspace-root "$P29_WS_N" --global-state-root "$P29_STATE_N" \
    --permit-token "$P29_TOKEN_DISC" 2>/dev/null)
  P29_RC_N=$?
  set -e
  if [ "$P29_RC_N" -eq 0 ] && echo "$P29_OUT_N" | grep -q "^HONGZHI_INDEX_BLOCK " && \
     [ ! -f "$P29_STATE_N/federated_index.json" ]; then
    check "Phase29:token_scope_missing_federated_index_non_strict_warn" "PASS"
  else
    check "Phase29:token_scope_missing_federated_index_non_strict_warn" "FAIL"
  fi

  # 8) governance disabled -> zero writes including federated index
  P29_WS_G="$REGRESSION_TMP/phase29_ws_governance"
  P29_STATE_G="$REGRESSION_TMP/phase29_state_governance"
  rm -rf "$P29_WS_G" "$P29_STATE_G"
  mkdir -p "$P29_WS_G" "$P29_STATE_G"
  set +e
  unset HONGZHI_PLUGIN_ENABLE 2>/dev/null || true
  "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --workspace-root "$P29_WS_G" --global-state-root "$P29_STATE_G" > /dev/null 2>&1
  P29_RC_G=$?
  set -e
  P29_G_WRITES=$(find "$P29_WS_G" "$P29_STATE_G" -type f \
    \( -name "federated_index.json" -o -name "federated_index.jsonl" -o -name "index.json" -o -name "capability_index.json" -o -name "latest.json" -o -name "run_meta.json" -o -name "capabilities.json" -o -name "capabilities.jsonl" -o -name "hints.json" \) | wc -l | tr -d ' ')
  if [ "$P29_RC_G" -eq 10 ] && [ "$P29_G_WRITES" = "0" ]; then
    check "Phase29:governance_disabled_zero_write_federated" "PASS"
  else
    check "Phase29:governance_disabled_zero_write_federated" "FAIL"
  fi
else
  check "Phase29:federated_index_smoke" "FAIL"
  check "Phase29:index_list_smoke" "FAIL"
  check "Phase29:index_query_strict_filters_limits_hit" "FAIL"
  check "Phase29:index_query_include_limits_hit" "FAIL"
  check "Phase29:index_explain_smoke" "FAIL"
  check "Phase29:token_scope_missing_federated_index_strict_exit24" "FAIL"
  check "Phase29:token_scope_missing_federated_index_non_strict_warn" "FAIL"
  check "Phase29:governance_disabled_zero_write_federated" "FAIL"
fi


# ─── Phase 30: plugin_v4_plus_hardening_round24 ───
echo "[phase 30] plugin_v4_plus_hardening_round24"
if [ -f "$PLUGIN" ] && [ -d "$CASE1" ] && [ -d "$CASE5" ] && [ -d "$CASE8" ]; then
  P30_TMP_REPO="$REGRESSION_TMP/phase30_repo"
  P30_WS="$REGRESSION_TMP/phase30_ws"
  P30_STATE="$REGRESSION_TMP/phase30_state"
  rm -rf "$P30_TMP_REPO" "$P30_WS" "$P30_STATE"
  mkdir -p "$P30_TMP_REPO" "$P30_WS" "$P30_STATE"

  # 1) status/index should not touch workspace/state when governance disabled.
  P30_SIG_BEFORE=$(snapshot_sig "$P30_WS" "$P30_STATE")
  set +e
  unset HONGZHI_PLUGIN_ENABLE 2>/dev/null || true
  P30_STATUS_OUT=$("$PYTHON_BIN" "$PLUGIN" status \
    --repo-root "$P30_TMP_REPO" --workspace-root "$P30_WS" --global-state-root "$P30_STATE" 2>/dev/null)
  P30_STATUS_RC=$?
  P30_INDEX_OUT=$("$PYTHON_BIN" "$PLUGIN" index list --global-state-root "$P30_STATE" --top-k 2 2>/dev/null)
  P30_INDEX_RC=$?
  set -e
  P30_SIG_AFTER=$(snapshot_sig "$P30_WS" "$P30_STATE")
  if [ "$P30_STATUS_RC" -eq 10 ] && [ "$P30_INDEX_RC" -eq 0 ] && [ "$P30_SIG_BEFORE" = "$P30_SIG_AFTER" ]; then
    check "Phase30:status_index_zero_touch" "PASS"
  else
    check "Phase30:status_index_zero_touch" "FAIL"
  fi

  # 2) read-only guard must detect writes even with --max-files truncation on scanning stage.
  P30_GUARD_REPO="$REGRESSION_TMP/phase30_guard_repo"
  P30_GUARD_WS="$REGRESSION_TMP/phase30_guard_ws"
  P30_GUARD_STATE="$REGRESSION_TMP/phase30_guard_state"
  rm -rf "$P30_GUARD_REPO" "$P30_GUARD_WS" "$P30_GUARD_STATE"
  "$PYTHON_BIN" - <<PY
import pathlib
root = pathlib.Path("$P30_GUARD_REPO")
for i in range(320):
    d = root / "src/main/java/com/example/guard" / f"m{i:03d}"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"C{i:03d}.java").write_text(
        f"package com.example.guard.m{i:03d};\\npublic class C{i:03d} {{}}\\n",
        encoding="utf-8",
    )
tail = root / "zz_tail"
tail.mkdir(parents=True, exist_ok=True)
(tail / "late.txt").write_text("before\\n", encoding="utf-8")
PY
  mkdir -p "$P30_GUARD_WS" "$P30_GUARD_STATE"
  (
    for i in $(seq 1 220); do
      printf 'mutated-%s\n' "$i" >> "$P30_GUARD_REPO/zz_tail/late.txt"
      sleep 0.01
    done
  ) &
  P30_BG_PID=$!
  set +e
  HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$P30_GUARD_REPO" --workspace-root "$P30_GUARD_WS" --global-state-root "$P30_GUARD_STATE" \
    --max-files 10 --top-k 3 > /dev/null 2>&1
  P30_GUARD_RC=$?
  set -e
  wait "$P30_BG_PID" 2>/dev/null || true
  if [ "$P30_GUARD_RC" -eq 3 ]; then
    check "Phase30:read_only_guard_not_truncated_by_max_files" "PASS"
  else
    check "Phase30:read_only_guard_not_truncated_by_max_files" "FAIL"
  fi

  # 3) policy parser fail-closed.
  P30_POLICY="$REGRESSION_TMP/phase30_policy"
  rm -rf "$P30_POLICY"
  mkdir -p "$P30_POLICY/allowed"
  cat > "$P30_POLICY/policy.yaml" <<EOF
plugin:
  enabled: true
  allow_roots:
    - "$P30_POLICY/allowed"
  deny_roots: []
  unexpected_block:
    - "bad"
EOF
  set +e
  P30_POLICY_OUT_STATUS=$("$PYTHON_BIN" "$PLUGIN" status \
    --repo-root "$P30_POLICY/allowed" --kit-root "$P30_POLICY" 2>/dev/null)
  P30_POLICY_RC_STATUS=$?
  P30_POLICY_OUT_DISC=$("$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --workspace-root "$P30_WS" --global-state-root "$P30_STATE" \
    --kit-root "$P30_POLICY" 2>/dev/null)
  P30_POLICY_RC_DISC=$?
  set -e
  if [ "$P30_POLICY_RC_STATUS" -eq 13 ] && [ "$P30_POLICY_RC_DISC" -eq 13 ] && \
     echo "$P30_POLICY_OUT_STATUS" | grep -q "^HONGZHI_GOV_BLOCK " && \
     echo "$P30_POLICY_OUT_DISC" | grep -q "reason=policy_parse_error"; then
    check "Phase30:policy_parse_fail_closed" "PASS"
  else
    check "Phase30:policy_parse_fail_closed" "FAIL"
  fi

  # 4) machine path parsing with spaces is stable via path=...
  P30_WS_SPACE="$REGRESSION_TMP/phase30 ws"
  P30_STATE_SPACE="$REGRESSION_TMP/phase30 state"
  rm -rf "$P30_WS_SPACE" "$P30_STATE_SPACE"
  mkdir -p "$P30_WS_SPACE" "$P30_STATE_SPACE"
  set +e
  P30_OUT_SPACE=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --workspace-root "$P30_WS_SPACE" --global-state-root "$P30_STATE_SPACE" \
    --keywords notice 2>/dev/null)
  P30_RC_SPACE=$?
  set -e
  P30_CAP_LINE_SPACE=$(printf '%s\n' "$P30_OUT_SPACE" | grep '^HONGZHI_CAPS ' | head -n 1 || true)
  P30_CAP_PATH_SPACE=$(extract_machine_path "$P30_CAP_LINE_SPACE")
  if [ "$P30_RC_SPACE" -eq 0 ] && [ -n "$P30_CAP_PATH_SPACE" ] && [ -f "$P30_CAP_PATH_SPACE" ] && \
     echo "$P30_CAP_LINE_SPACE" | grep -q 'path='; then
    check "Phase30:machine_line_path_with_spaces_safe" "PASS"
  else
    check "Phase30:machine_line_path_with_spaces_safe" "FAIL"
  fi

  # 5) jsonl append should be concurrency-safe with no line loss.
  P30_WS_CON="$REGRESSION_TMP/phase30_ws_con"
  P30_STATE_CON="$REGRESSION_TMP/phase30_state_con"
  rm -rf "$P30_WS_CON" "$P30_STATE_CON"
  mkdir -p "$P30_WS_CON" "$P30_STATE_CON"
  P30_CON_OK=$("$PYTHON_BIN" - <<PY
import importlib.util
import json
import os
import pathlib
import subprocess
import sys

repo_root = pathlib.Path("$REPO_ROOT")
plugin = pathlib.Path("$PLUGIN")
case1 = pathlib.Path("$CASE1")
ws = pathlib.Path("$P30_WS_CON")
state = pathlib.Path("$P30_STATE_CON")
py = "$PYTHON_BIN"
env = os.environ.copy()
env["HONGZHI_PLUGIN_ENABLE"] = "1"

procs = []
for _ in range(20):
    cmd = [
        py, str(plugin), "discover",
        "--repo-root", str(case1),
        "--workspace-root", str(ws),
        "--global-state-root", str(state),
        "--keywords", "notice",
    ]
    procs.append(subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, text=True))

rcs = [p.wait() for p in procs]
if any(rc != 0 for rc in rcs):
    print("0")
    sys.exit(0)

sys.path.insert(0, str(repo_root / "prompt-dsl-system/tools"))
spec = importlib.util.spec_from_file_location("hongzhi_plugin", str(plugin))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
fp = mod.compute_project_fingerprint(case1.resolve())
cap_jsonl = ws / fp / "capabilities.jsonl"
fed_jsonl = state / "federated_index.jsonl"

def _count_valid(path: pathlib.Path) -> tuple[int, bool]:
    if not path.is_file():
        return 0, False
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    ok = True
    for ln in lines:
        try:
            json.loads(ln)
        except Exception:
            ok = False
            break
    return len(lines), ok

cap_n, cap_ok = _count_valid(cap_jsonl)
fed_n, fed_ok = _count_valid(fed_jsonl)
print("1" if cap_n == 20 and fed_n == 20 and cap_ok and fed_ok else "0")
PY
)
  if [ "$P30_CON_OK" = "1" ]; then
    check "Phase30:jsonl_append_concurrency_no_loss" "PASS"
  else
    check "Phase30:jsonl_append_concurrency_no_loss" "FAIL"
  fi

  # 6) discover I/O optimization should keep outputs stable and expose scan_io_stats.
  P30_WS_IO="$REGRESSION_TMP/phase30_ws_io"
  P30_STATE_IO="$REGRESSION_TMP/phase30_state_io"
  rm -rf "$P30_WS_IO" "$P30_STATE_IO"
  mkdir -p "$P30_WS_IO" "$P30_STATE_IO"
  set +e
  P30_OUT_IO1=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --workspace-root "$P30_WS_IO" --global-state-root "$P30_STATE_IO" \
    --keywords notice 2>/dev/null)
  P30_RC_IO1=$?
  P30_OUT_IO2=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --workspace-root "$P30_WS_IO" --global-state-root "$P30_STATE_IO" \
    --keywords notice 2>/dev/null)
  P30_RC_IO2=$?
  set -e
  P30_CAP_IO1=$(extract_machine_path "$(printf '%s\n' "$P30_OUT_IO1" | grep '^HONGZHI_CAPS ' | head -n 1 || true)")
  P30_CAP_IO2=$(extract_machine_path "$(printf '%s\n' "$P30_OUT_IO2" | grep '^HONGZHI_CAPS ' | head -n 1 || true)")
  P30_IO_OK=$("$PYTHON_BIN" - <<PY
import json, pathlib
c1 = pathlib.Path("$P30_CAP_IO1")
c2 = pathlib.Path("$P30_CAP_IO2")
ok = False
if c1.is_file() and c2.is_file():
    a = json.loads(c1.read_text(encoding="utf-8"))
    b = json.loads(c2.read_text(encoding="utf-8"))
    am = a.get("module_candidates")
    bm = b.get("module_candidates")
    ae = a.get("metrics", {}).get("endpoints_total")
    be = b.get("metrics", {}).get("endpoints_total")
    io = b.get("scan_io_stats", {}) if isinstance(b.get("scan_io_stats"), dict) else {}
    ok = (
        am == bm and ae == be and
        int(io.get("layout_adapter_runs", 0) or 0) == 1 and
        "java_files_scanned" in io
    )
print("1" if ok else "0")
PY
)
  if [ "$P30_RC_IO1" -eq 0 ] && [ "$P30_RC_IO2" -eq 0 ] && [ "$P30_IO_OK" = "1" ]; then
    check "Phase30:discover_io_reduction_same_output" "PASS"
  else
    check "Phase30:discover_io_reduction_same_output" "FAIL"
  fi

  # 7) composed annotation / symbolic endpoint extraction.
  P30_WS_EP="$REGRESSION_TMP/phase30_ws_ep"
  P30_STATE_EP="$REGRESSION_TMP/phase30_state_ep"
  rm -rf "$P30_WS_EP" "$P30_STATE_EP"
  mkdir -p "$P30_WS_EP" "$P30_STATE_EP"
  set +e
  P30_OUT_EP=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE8" --workspace-root "$P30_WS_EP" --global-state-root "$P30_STATE_EP" \
    --keywords composed 2>/dev/null)
  P30_RC_EP=$?
  set -e
  P30_CAP_EP=$(extract_machine_path "$(printf '%s\n' "$P30_OUT_EP" | grep '^HONGZHI_CAPS ' | head -n 1 || true)")
  P30_EP_OK=$("$PYTHON_BIN" - <<PY
import json, pathlib
cap = pathlib.Path("$P30_CAP_EP")
ok = False
if cap.is_file():
    data = json.loads(cap.read_text(encoding="utf-8"))
    endpoints = int(data.get("metrics", {}).get("endpoints_total", 0) or 0)
    artifacts = data.get("artifacts", []) if isinstance(data.get("artifacts"), list) else []
    symbolic = False
    for ap in artifacts:
        p = pathlib.Path(ap)
        if p.is_file() and p.suffix == ".yaml":
            text = p.read_text(encoding="utf-8", errors="ignore")
            if "symbolic: 1" in text or "API." in text:
                symbolic = True
                break
    ok = endpoints > 0 and symbolic
print("1" if ok else "0")
PY
)
  if [ "$P30_RC_EP" -eq 0 ] && [ "$P30_EP_OK" = "1" ]; then
    check "Phase30:endpoint_composed_annotation_extracts" "PASS"
  else
    check "Phase30:endpoint_composed_annotation_extracts" "FAIL"
  fi

  # 8) apply-hints should expose hint effectiveness signal.
  P30_WS_HINT="$REGRESSION_TMP/phase30_ws_hint"
  P30_STATE_HINT="$REGRESSION_TMP/phase30_state_hint"
  rm -rf "$P30_WS_HINT" "$P30_STATE_HINT"
  mkdir -p "$P30_WS_HINT" "$P30_STATE_HINT"
  set +e
  P30_OUT_HINT1=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE5" --workspace-root "$P30_WS_HINT" --global-state-root "$P30_STATE_HINT" \
    --strict 2>/dev/null)
  P30_RC_HINT1=$?
  set -e
  P30_HINT_PATH=$(extract_machine_path "$(printf '%s\n' "$P30_OUT_HINT1" | grep '^HONGZHI_HINTS ' | head -n 1 || true)")
  set +e
  P30_OUT_HINT2=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE5" --workspace-root "$P30_WS_HINT" --global-state-root "$P30_STATE_HINT" \
    --strict --apply-hints "$P30_HINT_PATH" --hint-strategy aggressive 2>/dev/null)
  P30_RC_HINT2=$?
  set -e
  P30_CAP_HINT2=$(extract_machine_path "$(printf '%s\n' "$P30_OUT_HINT2" | grep '^HONGZHI_CAPS ' | head -n 1 || true)")
  P30_HINT_OK=$("$PYTHON_BIN" - <<PY
import json, pathlib
cap = pathlib.Path("$P30_CAP_HINT2")
ok = False
if cap.is_file():
    data = json.loads(cap.read_text(encoding="utf-8"))
    hints = data.get("hints", {}) if isinstance(data.get("hints"), dict) else {}
    delta = float(hints.get("confidence_delta", 0.0) or 0.0)
    ok = bool(hints.get("applied", False)) and (bool(hints.get("hint_effective", False)) or delta > 0.0)
print("1" if ok else "0")
PY
)
  if [ "$P30_RC_HINT1" -eq 21 ] && [ "$P30_RC_HINT2" -eq 0 ] && \
     echo "$P30_OUT_HINT2" | grep -q "hint_applied=1" && [ "$P30_HINT_OK" = "1" ]; then
    check "Phase30:hint_apply_effectiveness_signal" "PASS"
  else
    check "Phase30:hint_apply_effectiveness_signal" "FAIL"
  fi
else
  check "Phase30:status_index_zero_touch" "FAIL"
  check "Phase30:read_only_guard_not_truncated_by_max_files" "FAIL"
  check "Phase30:policy_parse_fail_closed" "FAIL"
  check "Phase30:machine_line_path_with_spaces_safe" "FAIL"
  check "Phase30:jsonl_append_concurrency_no_loss" "FAIL"
  check "Phase30:discover_io_reduction_same_output" "FAIL"
  check "Phase30:endpoint_composed_annotation_extracts" "FAIL"
  check "Phase30:hint_apply_effectiveness_signal" "FAIL"
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
