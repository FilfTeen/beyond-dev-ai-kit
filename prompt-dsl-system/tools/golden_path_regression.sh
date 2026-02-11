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
