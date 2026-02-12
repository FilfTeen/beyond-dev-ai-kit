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

usage() {
  cat <<'EOF'
Usage:
  bash prompt-dsl-system/tools/golden_path_regression.sh \
    [--repo-root <path>] \
    [--tmp-dir <path>] \
    [--report-out <path>] \
    [--clean-tmp] \
    [--shard-group <all|early|mid|late>]
EOF
}

REPO_ROOT="."
REPO_ROOT_SET="false"
TMP_DIR=""
REPORT_OUT=""
CLEAN_TMP="false"
SHARD_GROUP="all"
while [ $# -gt 0 ]; do
  case "$1" in
    --repo-root)
      shift
      if [ $# -eq 0 ]; then
        echo "error: --repo-root requires a path" >&2
        usage >&2
        exit 2
      fi
      REPO_ROOT="$1"
      REPO_ROOT_SET="true"
      ;;
    --tmp-dir)
      shift
      if [ $# -eq 0 ]; then
        echo "error: --tmp-dir requires a path" >&2
        usage >&2
        exit 2
      fi
      TMP_DIR="$1"
      ;;
    --report-out)
      shift
      if [ $# -eq 0 ]; then
        echo "error: --report-out requires a path" >&2
        usage >&2
        exit 2
      fi
      REPORT_OUT="$1"
      ;;
    --clean-tmp)
      CLEAN_TMP="true"
      ;;
    --shard-group)
      shift
      if [ $# -eq 0 ]; then
        echo "error: --shard-group requires a value" >&2
        usage >&2
        exit 2
      fi
      SHARD_GROUP="$1"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --*)
      echo "error: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [ "$REPO_ROOT_SET" = "true" ]; then
        echo "error: unexpected positional argument: $1" >&2
        usage >&2
        exit 2
      fi
      REPO_ROOT="$1"
      REPO_ROOT_SET="true"
      ;;
  esac
  shift
done

if [ ! -d "$REPO_ROOT" ]; then
  echo "error: repo root does not exist or is not a directory: $REPO_ROOT" >&2
  exit 2
fi
REPO_ROOT="$(cd "$REPO_ROOT" && pwd)"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"
SKILLS_JSON="$REPO_ROOT/prompt-dsl-system/05_skill_registry/skills.json"
SKILLS_DIR="$REPO_ROOT/prompt-dsl-system/05_skill_registry/skills"
TEMPLATE_DIR="$REPO_ROOT/prompt-dsl-system/05_skill_registry/templates/skill_template"
if [ -z "$TMP_DIR" ]; then
  REGRESSION_TMP="$REPO_ROOT/_regression_tmp"
elif [[ "$TMP_DIR" = /* ]]; then
  REGRESSION_TMP="$TMP_DIR"
else
  REGRESSION_TMP="$REPO_ROOT/$TMP_DIR"
fi

if [ -z "$REPORT_OUT" ]; then
  REPORT_OUT_PATH=""
elif [[ "$REPORT_OUT" = /* ]]; then
  REPORT_OUT_PATH="$REPORT_OUT"
else
  REPORT_OUT_PATH="$REPO_ROOT/$REPORT_OUT"
fi

REPORT_TIMESTAMP="${HONGZHI_GOLDEN_REPORT_TIMESTAMP:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
REPORT_FILE="$REGRESSION_TMP/regression_report.md"
SKILLS_BAK_FILE="$REGRESSION_TMP/skills.json.bak"

RUN_EARLY="false"
RUN_MID="false"
RUN_LATE="false"
case "$SHARD_GROUP" in
  all)
    RUN_EARLY="true"
    RUN_MID="true"
    RUN_LATE="true"
    ;;
  early)
    RUN_EARLY="true"
    ;;
  mid)
    RUN_MID="true"
    ;;
  late)
    RUN_LATE="true"
    ;;
  *)
    echo "error: invalid --shard-group: $SHARD_GROUP (expected all|early|mid|late)" >&2
    exit 2
    ;;
esac

CLEANUP_DONE="false"
cleanup_state() {
  if [ "$CLEANUP_DONE" = "true" ]; then
    return
  fi
  CLEANUP_DONE="true"

  if [ -f "$SKILLS_BAK_FILE" ]; then
    cp "$SKILLS_BAK_FILE" "$SKILLS_JSON" 2>/dev/null || true
  fi

  if [ -n "${SIM_SKILL_DIR:-}" ] && [ -d "${SIM_SKILL_DIR:-}" ]; then
    rm -rf "$SIM_SKILL_DIR" 2>/dev/null || true
  fi

  if [ -n "${SIM_DOMAIN:-}" ] && [ -d "$SKILLS_DIR/$SIM_DOMAIN" ]; then
    rmdir "$SKILLS_DIR/$SIM_DOMAIN" 2>/dev/null || true
  fi
}

trap cleanup_state EXIT
trap 'cleanup_state; exit 130' INT
trap 'cleanup_state; exit 143' TERM

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
echo "shard-group: $SHARD_GROUP"
echo ""

# Cleanup previous runs
rm -rf "$REGRESSION_TMP"
mkdir -p "$REGRESSION_TMP"

# Shared fixtures (needed by shard execution too).
CASE1="$SCRIPT_DIR/_tmp_structure_cases/case1_standard"
CASE2="$SCRIPT_DIR/_tmp_structure_cases/case2_classlevel"
CASE4="$SCRIPT_DIR/_tmp_structure_cases/case4_endpoint_miss"
CASE5="$SCRIPT_DIR/_tmp_structure_cases/case5_ambiguous_two_modules"
CASE6="$SCRIPT_DIR/_tmp_structure_cases/case6_maven_multi_module"
CASE7="$SCRIPT_DIR/_tmp_structure_cases/case7_nonstandard_java_root"
CASE8="$SCRIPT_DIR/_tmp_structure_cases/case8_composed_annotation"
CASE9="$SCRIPT_DIR/_tmp_structure_cases/case7_scan_graph_weird_annotations"
PLUGIN="$SCRIPT_DIR/hongzhi_plugin.py"
PLUGIN_STATE="$REGRESSION_TMP/plugin_global_state"
mkdir -p "$PLUGIN_STATE"

if [ "$RUN_EARLY" = "true" ]; then
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
cp "$SKILLS_JSON" "$SKILLS_BAK_FILE"
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
CASE9="$SCRIPT_DIR/_tmp_structure_cases/case7_scan_graph_weird_annotations"
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

fi

if [ "$RUN_MID" = "true" ]; then
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
    lines = text.splitlines()
    start_idx = -1
    for i, line in enumerate(lines):
        if line.lstrip().startswith("{"):
            start_idx = i
            break
    data = json.loads("\n".join(lines[start_idx:])) if start_idx >= 0 else {}
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


# ─── Phase 31: unified_scan_graph_round25 ───
echo "[phase 31] unified_scan_graph_round25"
SCAN_GRAPH_SCRIPT="$SCRIPT_DIR/scan_graph.py"
if [ -f "$PLUGIN" ] && [ -f "$SCAN_GRAPH_SCRIPT" ] && [ -d "$CASE1" ] && [ -d "$CASE9" ]; then
  P31_WS="$REGRESSION_TMP/phase31_ws"
  P31_STATE="$REGRESSION_TMP/phase31_state"
  rm -rf "$P31_WS" "$P31_STATE"
  mkdir -p "$P31_WS" "$P31_STATE"

  # 1) scan_graph_syntax_smoke + schema presence
  set +e
  "$PYTHON_BIN" "$SCAN_GRAPH_SCRIPT" --help > /dev/null 2>&1
  P31_HELP_RC=$?
  "$PYTHON_BIN" "$SCAN_GRAPH_SCRIPT" \
    --repo-root "$CASE1" \
    --workspace-root "$P31_WS" \
    --out "$P31_WS/scan_graph_smoke.json" \
    --keywords "notice" > /dev/null 2>&1
  P31_SG_RC=$?
  set -e
  P31_SG_OK=$("$PYTHON_BIN" - <<PY
import json, pathlib
p = pathlib.Path("$P31_WS/scan_graph_smoke.json")
ok = False
if p.is_file():
    data = json.loads(p.read_text(encoding="utf-8"))
    ok = isinstance(data.get("file_index"), dict) and isinstance(data.get("io_stats"), dict) and bool(data.get("cache_key"))
print("1" if ok else "0")
PY
)
  if [ "$P31_HELP_RC" -eq 0 ] && [ "$P31_SG_RC" -eq 0 ] && [ "$P31_SG_OK" = "1" ]; then
    check "Phase31:scan_graph_syntax_smoke" "PASS"
  else
    check "Phase31:scan_graph_syntax_smoke" "FAIL"
  fi

  # 2) discover_uses_scan_graph
  set +e
  P31_DISC_OUT=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --workspace-root "$P31_WS" --global-state-root "$P31_STATE" \
    --keywords notice 2>/dev/null)
  P31_DISC_RC=$?
  set -e
  P31_DISC_CAP=$(extract_machine_path "$(printf '%s\n' "$P31_DISC_OUT" | grep '^HONGZHI_CAPS ' | head -n 1 || true)")
  P31_DISC_OK=$("$PYTHON_BIN" - <<PY
import json, pathlib
cap = pathlib.Path("$P31_DISC_CAP")
ok = False
if cap.is_file():
    data = json.loads(cap.read_text(encoding="utf-8"))
    sg = data.get("scan_graph", {})
    ok = bool(sg.get("used", False))
print("1" if ok else "0")
PY
)
  if [ "$P31_DISC_RC" -eq 0 ] && echo "$P31_DISC_OUT" | grep -q "scan_graph_used=1" && [ "$P31_DISC_OK" = "1" ]; then
    check "Phase31:discover_uses_scan_graph" "PASS"
  else
    check "Phase31:discover_uses_scan_graph" "FAIL"
  fi

  # 3) scan_graph_cache_warm_hit
  set +e
  "$PYTHON_BIN" "$SCAN_GRAPH_SCRIPT" \
    --repo-root "$CASE1" \
    --workspace-root "$P31_WS" \
    --out "$P31_WS/scan_graph_warm_1.json" \
    --keywords "notice" > /dev/null 2>&1
  P31_WARM1_RC=$?
  "$PYTHON_BIN" "$SCAN_GRAPH_SCRIPT" \
    --repo-root "$CASE1" \
    --workspace-root "$P31_WS" \
    --out "$P31_WS/scan_graph_warm_2.json" \
    --keywords "notice" > /dev/null 2>&1
  P31_WARM2_RC=$?
  set -e
  P31_WARM_OK=$("$PYTHON_BIN" - <<PY
import json, pathlib
p = pathlib.Path("$P31_WS/scan_graph_warm_2.json")
ok = False
if p.is_file():
    data = json.loads(p.read_text(encoding="utf-8"))
    io = data.get("io_stats", {}) if isinstance(data.get("io_stats"), dict) else {}
    ok = float(io.get("cache_hit_rate", 0.0) or 0.0) >= 0.99
print("1" if ok else "0")
PY
)
  if [ "$P31_WARM1_RC" -eq 0 ] && [ "$P31_WARM2_RC" -eq 0 ] && [ "$P31_WARM_OK" = "1" ]; then
    check "Phase31:scan_graph_cache_warm_hit" "PASS"
  else
    check "Phase31:scan_graph_cache_warm_hit" "FAIL"
  fi

  # 4) discover_io_reduction_delta
  P31_WS_IO="$REGRESSION_TMP/phase31_ws_io"
  P31_STATE_IO="$REGRESSION_TMP/phase31_state_io"
  rm -rf "$P31_WS_IO" "$P31_STATE_IO"
  mkdir -p "$P31_WS_IO" "$P31_STATE_IO"
  set +e
  P31_IO_OUT1=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --workspace-root "$P31_WS_IO" --global-state-root "$P31_STATE_IO" \
    --keywords notice 2>/dev/null)
  P31_IO_RC1=$?
  P31_IO_OUT2=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --workspace-root "$P31_WS_IO" --global-state-root "$P31_STATE_IO" \
    --keywords notice 2>/dev/null)
  P31_IO_RC2=$?
  set -e
  P31_IO_CAP1=$(extract_machine_path "$(printf '%s\n' "$P31_IO_OUT1" | grep '^HONGZHI_CAPS ' | head -n 1 || true)")
  P31_IO_CAP2=$(extract_machine_path "$(printf '%s\n' "$P31_IO_OUT2" | grep '^HONGZHI_CAPS ' | head -n 1 || true)")
  P31_IO_OK=$("$PYTHON_BIN" - <<PY
import json, pathlib
c1 = pathlib.Path("$P31_IO_CAP1")
c2 = pathlib.Path("$P31_IO_CAP2")
ok = False
if c1.is_file() and c2.is_file():
    d1 = json.loads(c1.read_text(encoding="utf-8"))
    d2 = json.loads(c2.read_text(encoding="utf-8"))
    b1 = int(((d1.get("scan_graph", {}) or {}).get("bytes_read", 0)) or 0)
    b2 = int(((d2.get("scan_graph", {}) or {}).get("bytes_read", 0)) or 0)
    m1 = int(d1.get("module_candidates", 0) or 0)
    m2 = int(d2.get("module_candidates", 0) or 0)
    e1 = int((d1.get("metrics", {}) or {}).get("endpoints_total", 0) or 0)
    e2 = int((d2.get("metrics", {}) or {}).get("endpoints_total", 0) or 0)
    ok = (m1 == m2 and e1 == e2 and b2 <= b1)
print("1" if ok else "0")
PY
)
  if [ "$P31_IO_RC1" -eq 0 ] && [ "$P31_IO_RC2" -eq 0 ] && [ "$P31_IO_OK" = "1" ]; then
    check "Phase31:discover_io_reduction_delta" "PASS"
  else
    check "Phase31:discover_io_reduction_delta" "FAIL"
  fi

  # 5) profile_reuses_scan_graph
  P31_PROFILE_SG="$P31_WS/profile_scan_graph.json"
  "$PYTHON_BIN" "$SCAN_GRAPH_SCRIPT" \
    --repo-root "$CASE1" \
    --workspace-root "$P31_WS" \
    --out "$P31_PROFILE_SG" \
    --keywords "notice" > /dev/null 2>&1
  set +e
  P31_PROF_OUT=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" profile \
    --repo-root "$CASE1" --workspace-root "$P31_WS" --global-state-root "$P31_STATE" \
    --module-key notice --scan-graph "$P31_PROFILE_SG" 2>/dev/null)
  P31_PROF_RC=$?
  set -e
  P31_PROF_CAP=$(extract_machine_path "$(printf '%s\n' "$P31_PROF_OUT" | grep '^HONGZHI_CAPS ' | head -n 1 || true)")
  P31_PROF_OK=$("$PYTHON_BIN" - <<PY
import json, pathlib
cap = pathlib.Path("$P31_PROF_CAP")
ok = False
if cap.is_file():
    data = json.loads(cap.read_text(encoding="utf-8"))
    ok = bool((data.get("scan_graph", {}) or {}).get("used", False))
print("1" if ok else "0")
PY
)
  if [ "$P31_PROF_RC" -eq 0 ] && [ "$P31_PROF_OK" = "1" ] && echo "$P31_PROF_OUT" | grep -q "scan_graph_used=1"; then
    check "Phase31:profile_reuses_scan_graph" "PASS"
  else
    check "Phase31:profile_reuses_scan_graph" "FAIL"
  fi

  # 6) diff_reuses_scan_graph
  P31_DIFF_OLD="$REGRESSION_TMP/phase31_diff_old"
  P31_DIFF_NEW="$REGRESSION_TMP/phase31_diff_new"
  P31_DIFF_WS="$REGRESSION_TMP/phase31_diff_ws"
  P31_DIFF_STATE="$REGRESSION_TMP/phase31_diff_state"
  rm -rf "$P31_DIFF_OLD" "$P31_DIFF_NEW" "$P31_DIFF_WS" "$P31_DIFF_STATE"
  cp -R "$CASE1" "$P31_DIFF_OLD"
  cp -R "$CASE1" "$P31_DIFF_NEW"
  mkdir -p "$P31_DIFF_WS" "$P31_DIFF_STATE"
  printf '\n// diff marker\n' >> "$P31_DIFF_NEW/src/main/java/com/example/notice/controller/NoticeController.java"
  "$PYTHON_BIN" "$SCAN_GRAPH_SCRIPT" --repo-root "$P31_DIFF_OLD" --workspace-root "$P31_DIFF_WS" --out "$P31_DIFF_WS/old_scan_graph.json" > /dev/null 2>&1
  "$PYTHON_BIN" "$SCAN_GRAPH_SCRIPT" --repo-root "$P31_DIFF_NEW" --workspace-root "$P31_DIFF_WS" --out "$P31_DIFF_WS/new_scan_graph.json" > /dev/null 2>&1
  set +e
  P31_DIFF_OUT=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" diff \
    --old-project-root "$P31_DIFF_OLD" --new-project-root "$P31_DIFF_NEW" \
    --module-key notice \
    --old-scan-graph "$P31_DIFF_WS/old_scan_graph.json" \
    --new-scan-graph "$P31_DIFF_WS/new_scan_graph.json" \
    --workspace-root "$P31_DIFF_WS" --global-state-root "$P31_DIFF_STATE" 2>/dev/null)
  P31_DIFF_RC=$?
  set -e
  P31_DIFF_CAP=$(extract_machine_path "$(printf '%s\n' "$P31_DIFF_OUT" | grep '^HONGZHI_CAPS ' | head -n 1 || true)")
  P31_DIFF_OK=$("$PYTHON_BIN" - <<PY
import json, pathlib
cap = pathlib.Path("$P31_DIFF_CAP")
ok = False
if cap.is_file():
    data = json.loads(cap.read_text(encoding="utf-8"))
    ok = bool((data.get("scan_graph", {}) or {}).get("used", False))
print("1" if ok else "0")
PY
)
  if [ "$P31_DIFF_RC" -eq 0 ] && [ "$P31_DIFF_OK" = "1" ] && echo "$P31_DIFF_OUT" | grep -q "scan_graph_used=1"; then
    check "Phase31:diff_reuses_scan_graph" "PASS"
  else
    check "Phase31:diff_reuses_scan_graph" "FAIL"
  fi

  # 7) governance_disabled_zero_write_still (status/index/scan-graph/discover)
  P31_WS_G="$REGRESSION_TMP/phase31_ws_gov"
  P31_STATE_G="$REGRESSION_TMP/phase31_state_gov"
  rm -rf "$P31_WS_G" "$P31_STATE_G"
  mkdir -p "$P31_WS_G" "$P31_STATE_G"
  P31_SIG_BEFORE=$(snapshot_sig "$P31_WS_G" "$P31_STATE_G")
  set +e
  unset HONGZHI_PLUGIN_ENABLE 2>/dev/null || true
  "$PYTHON_BIN" "$PLUGIN" status --repo-root "$CASE1" --workspace-root "$P31_WS_G" --global-state-root "$P31_STATE_G" > /dev/null 2>&1
  P31_G_RC_STATUS=$?
  "$PYTHON_BIN" "$PLUGIN" index list --global-state-root "$P31_STATE_G" > /dev/null 2>&1
  P31_G_RC_INDEX=$?
  "$PYTHON_BIN" "$PLUGIN" scan-graph --repo-root "$CASE1" --workspace-root "$P31_WS_G" --global-state-root "$P31_STATE_G" > /dev/null 2>&1
  P31_G_RC_SCAN=$?
  "$PYTHON_BIN" "$PLUGIN" discover --repo-root "$CASE1" --workspace-root "$P31_WS_G" --global-state-root "$P31_STATE_G" > /dev/null 2>&1
  P31_G_RC_DISC=$?
  set -e
  P31_SIG_AFTER=$(snapshot_sig "$P31_WS_G" "$P31_STATE_G")
  if [ "$P31_G_RC_STATUS" -eq 10 ] && [ "$P31_G_RC_INDEX" -eq 0 ] && [ "$P31_G_RC_SCAN" -eq 10 ] && [ "$P31_G_RC_DISC" -eq 10 ] && [ "$P31_SIG_BEFORE" = "$P31_SIG_AFTER" ]; then
    check "Phase31:governance_disabled_zero_write_still" "PASS"
  else
    check "Phase31:governance_disabled_zero_write_still" "FAIL"
  fi

  # 8) strict_mismatch_exit25
  P31_WS_M="$REGRESSION_TMP/phase31_ws_mismatch"
  P31_STATE_M="$REGRESSION_TMP/phase31_state_mismatch"
  rm -rf "$P31_WS_M" "$P31_STATE_M"
  mkdir -p "$P31_WS_M" "$P31_STATE_M"
  set +e
  P31_M_OUT_STRICT=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE9" --workspace-root "$P31_WS_M" --global-state-root "$P31_STATE_M" \
    --strict --keywords weird 2>/dev/null)
  P31_M_RC_STRICT=$?
  P31_M_OUT_NSTR=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE9" --workspace-root "$P31_WS_M" --global-state-root "$P31_STATE_M" \
    --keywords weird 2>/dev/null)
  P31_M_RC_NSTR=$?
  set -e
  if [ "$P31_M_RC_STRICT" -eq 25 ] && echo "$P31_M_OUT_STRICT" | grep -q "exit_hint=scan_graph_mismatch" && \
     [ "$P31_M_RC_NSTR" -eq 0 ] && echo "$P31_M_OUT_NSTR" | grep -q "scan_graph_used=1"; then
    check "Phase31:strict_mismatch_exit25" "PASS"
  else
    check "Phase31:strict_mismatch_exit25" "FAIL"
  fi
else
  check "Phase31:scan_graph_syntax_smoke" "FAIL"
  check "Phase31:discover_uses_scan_graph" "FAIL"
  check "Phase31:scan_graph_cache_warm_hit" "FAIL"
  check "Phase31:discover_io_reduction_delta" "FAIL"
  check "Phase31:profile_reuses_scan_graph" "FAIL"
  check "Phase31:diff_reuses_scan_graph" "FAIL"
  check "Phase31:governance_disabled_zero_write_still" "FAIL"
  check "Phase31:strict_mismatch_exit25" "FAIL"
fi

# ─── Phase 32: scan_graph_contract_v1_1_and_reuse_guard ───
echo "[phase 32] scan_graph_contract_v1_1_and_reuse_guard"
if [ -f "$PLUGIN" ] && [ -f "$SCAN_GRAPH_SCRIPT" ] && [ -d "$CASE1" ] && [ -d "$CASE5" ] && [ -d "$CASE9" ]; then
  P32_WS="$REGRESSION_TMP/phase32_ws"
  P32_STATE="$REGRESSION_TMP/phase32_state"
  rm -rf "$P32_WS" "$P32_STATE"
  mkdir -p "$P32_WS" "$P32_STATE"

  # 1) scan_graph schema/version/fingerprint fields present
  set +e
  P32_SG_OUT=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" scan-graph \
    --repo-root "$CASE1" --workspace-root "$P32_WS" --global-state-root "$P32_STATE" \
    --keywords notice 2>/dev/null)
  P32_SG_RC=$?
  set -e
  P32_SG_CAP=$(extract_machine_path "$(printf '%s\n' "$P32_SG_OUT" | grep '^HONGZHI_CAPS ' | head -n 1 || true)")
  P32_SG_OK=$("$PYTHON_BIN" - <<PY
import json, pathlib
cap = pathlib.Path("$P32_SG_CAP")
ok = False
if cap.is_file():
    data = json.loads(cap.read_text(encoding="utf-8"))
    sg = data.get("scan_graph", {}) if isinstance(data.get("scan_graph"), dict) else {}
    graph_path = pathlib.Path(str(sg.get("path", "") or ""))
    if graph_path.is_file():
        g = json.loads(graph_path.read_text(encoding="utf-8"))
        pv = g.get("producer_versions", {}) if isinstance(g.get("producer_versions"), dict) else {}
        ok = (
            str(g.get("schema_version", "")) != "" and
            str(g.get("graph_fingerprint", "")) != "" and
            str(pv.get("package_version", "")) != "" and
            str(pv.get("plugin_version", "")) != "" and
            str(pv.get("contract_version", "")) != ""
        )
print("1" if ok else "0")
PY
)
  if [ "$P32_SG_RC" -eq 0 ] && [ "$P32_SG_OK" = "1" ]; then
    check "Phase32:scan_graph_schema_version_present" "PASS"
  else
    check "Phase32:scan_graph_schema_version_present" "FAIL"
  fi

  # 2) strict mismatch should emit mismatch_reason/detail + exit_hint
  set +e
  P32_MISMATCH_OUT=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE9" --workspace-root "$P32_WS" --global-state-root "$P32_STATE" \
    --strict --keywords weird 2>/dev/null)
  P32_MISMATCH_RC=$?
  set -e
  P32_MISMATCH_SUM=$(printf '%s\n' "$P32_MISMATCH_OUT" | grep '^hongzhi_ai_kit_summary ' | head -n 1 || true)
  P32_MISMATCH_CAP=$(printf '%s\n' "$P32_MISMATCH_OUT" | grep '^HONGZHI_CAPS ' | head -n 1 || true)
  if [ "$P32_MISMATCH_RC" -eq 25 ] && \
     echo "$P32_MISMATCH_SUM" | grep -q 'exit_hint=scan_graph_mismatch' && \
     echo "$P32_MISMATCH_SUM" | grep -q 'mismatch_reason=' && \
     ! echo "$P32_MISMATCH_SUM" | grep -q 'mismatch_reason=-' && \
     echo "$P32_MISMATCH_CAP" | grep -q 'mismatch_reason='; then
    check "Phase32:scan_graph_strict_mismatch_reason_emitted" "PASS"
  else
    check "Phase32:scan_graph_strict_mismatch_reason_emitted" "FAIL"
  fi

  # 3) discover -> profile/diff default reuse: no rescan in profile/diff hot path
  P32_REUSE_WS="$REGRESSION_TMP/phase32_reuse_ws"
  P32_REUSE_STATE="$REGRESSION_TMP/phase32_reuse_state"
  rm -rf "$P32_REUSE_WS" "$P32_REUSE_STATE"
  mkdir -p "$P32_REUSE_WS" "$P32_REUSE_STATE"
  set +e
  P32_DISC_REUSE=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --workspace-root "$P32_REUSE_WS" --global-state-root "$P32_REUSE_STATE" \
    --keywords notice 2>/dev/null)
  P32_DISC_REUSE_RC=$?
  P32_PROF_REUSE=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" profile \
    --repo-root "$CASE1" --workspace-root "$P32_REUSE_WS" --global-state-root "$P32_REUSE_STATE" \
    --module-key notice 2>/dev/null)
  P32_PROF_REUSE_RC=$?
  P32_DIFF_REUSE=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" diff \
    --old-project-root "$CASE1" --new-project-root "$CASE1" --module-key notice \
    --workspace-root "$P32_REUSE_WS" --global-state-root "$P32_REUSE_STATE" 2>/dev/null)
  P32_DIFF_REUSE_RC=$?
  set -e
  P32_PROF_SUM=$(printf '%s\n' "$P32_PROF_REUSE" | grep '^hongzhi_ai_kit_summary ' | head -n 1 || true)
  P32_DIFF_SUM=$(printf '%s\n' "$P32_DIFF_REUSE" | grep '^hongzhi_ai_kit_summary ' | head -n 1 || true)
  if [ "$P32_DISC_REUSE_RC" -eq 0 ] && [ "$P32_PROF_REUSE_RC" -eq 0 ] && [ "$P32_DIFF_REUSE_RC" -eq 0 ] && \
     echo "$P32_PROF_SUM" | grep -q 'scan_graph_used=1' && \
     echo "$P32_DIFF_SUM" | grep -q 'scan_graph_used=1' && \
     { echo "$P32_PROF_SUM" | grep -q 'bytes_read=0' || echo "$P32_PROF_SUM" | grep -q 'java_files_indexed=0'; } && \
     { echo "$P32_DIFF_SUM" | grep -q 'bytes_read=0' || echo "$P32_DIFF_SUM" | grep -q 'java_files_indexed=0'; }; then
    check "Phase32:discover_profile_diff_reuse_no_rescan" "PASS"
  else
    check "Phase32:discover_profile_diff_reuse_no_rescan" "FAIL"
  fi

  # 4) machine line json payload additive (legacy fields retained)
  set +e
  P32_JSON_OUT=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE5" --workspace-root "$P32_WS" --global-state-root "$P32_STATE" 2>/dev/null)
  P32_JSON_RC=$?
  set -e
  P32_JSON_CAPS=$(printf '%s\n' "$P32_JSON_OUT" | grep '^HONGZHI_CAPS ' | head -n 1 || true)
  P32_JSON_INDEX=$(printf '%s\n' "$P32_JSON_OUT" | grep '^HONGZHI_INDEX ' | head -n 1 || true)
  P32_JSON_HINTS=$(printf '%s\n' "$P32_JSON_OUT" | grep '^HONGZHI_HINTS ' | head -n 1 || true)
  if [ "$P32_JSON_RC" -eq 0 ] && \
     echo "$P32_JSON_CAPS" | grep -q 'path=' && echo "$P32_JSON_CAPS" | grep -q "json='{" && \
     echo "$P32_JSON_CAPS" | grep -q 'package_version=' && \
     echo "$P32_JSON_INDEX" | grep -q 'path=' && echo "$P32_JSON_INDEX" | grep -q "json='{" && \
     { [ -z "$P32_JSON_HINTS" ] || { echo "$P32_JSON_HINTS" | grep -q 'path=' && echo "$P32_JSON_HINTS" | grep -q "json='{"; }; }; then
    check "Phase32:machine_line_json_payload_additive" "PASS"
  else
    check "Phase32:machine_line_json_payload_additive" "FAIL"
  fi

  # 5) governance disabled still zero write
  P32_G_WS="$REGRESSION_TMP/phase32_g_ws"
  P32_G_STATE="$REGRESSION_TMP/phase32_g_state"
  rm -rf "$P32_G_WS" "$P32_G_STATE"
  mkdir -p "$P32_G_WS" "$P32_G_STATE"
  P32_G_SIG_BEFORE=$(snapshot_sig "$P32_G_WS" "$P32_G_STATE")
  set +e
  unset HONGZHI_PLUGIN_ENABLE 2>/dev/null || true
  "$PYTHON_BIN" "$PLUGIN" status --repo-root "$CASE1" --workspace-root "$P32_G_WS" --global-state-root "$P32_G_STATE" > /dev/null 2>&1
  P32_G_RC_STATUS=$?
  "$PYTHON_BIN" "$PLUGIN" discover --repo-root "$CASE1" --workspace-root "$P32_G_WS" --global-state-root "$P32_G_STATE" > /dev/null 2>&1
  P32_G_RC_DISC=$?
  "$PYTHON_BIN" "$PLUGIN" scan-graph --repo-root "$CASE1" --workspace-root "$P32_G_WS" --global-state-root "$P32_G_STATE" > /dev/null 2>&1
  P32_G_RC_SCAN=$?
  "$PYTHON_BIN" "$PLUGIN" index list --global-state-root "$P32_G_STATE" > /dev/null 2>&1
  P32_G_RC_INDEX=$?
  set -e
  P32_G_SIG_AFTER=$(snapshot_sig "$P32_G_WS" "$P32_G_STATE")
  if [ "$P32_G_RC_STATUS" -eq 10 ] && [ "$P32_G_RC_DISC" -eq 10 ] && [ "$P32_G_RC_SCAN" -eq 10 ] && \
     [ "$P32_G_RC_INDEX" -eq 0 ] && [ "$P32_G_SIG_BEFORE" = "$P32_G_SIG_AFTER" ]; then
    check "Phase32:governance_disabled_zero_write_still" "PASS"
  else
    check "Phase32:governance_disabled_zero_write_still" "FAIL"
  fi

  # 6) read-only guard must remain full snapshot even with limits
  P32_GUARD_REPO="$REGRESSION_TMP/phase32_guard_repo"
  P32_GUARD_WS="$REGRESSION_TMP/phase32_guard_ws"
  P32_GUARD_STATE="$REGRESSION_TMP/phase32_guard_state"
  rm -rf "$P32_GUARD_REPO" "$P32_GUARD_WS" "$P32_GUARD_STATE"
  mkdir -p "$P32_GUARD_REPO"
  "$PYTHON_BIN" - <<PY
import pathlib
root = pathlib.Path("$P32_GUARD_REPO")
for i in range(260):
    d = root / "src/main/java/com/example/guard32" / f"m{i:03d}"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"G{i:03d}.java").write_text(
        f"package com.example.guard32.m{i:03d};\\npublic class G{i:03d} {{}}\\n",
        encoding="utf-8",
    )
tail = root / "zz_tail"
tail.mkdir(parents=True, exist_ok=True)
(tail / "late.txt").write_text("before\\n", encoding="utf-8")
PY
  mkdir -p "$P32_GUARD_WS" "$P32_GUARD_STATE"
  (
    for i in $(seq 1 220); do
      printf 'guard32-mutated-%s\n' "$i" >> "$P32_GUARD_REPO/zz_tail/late.txt"
      sleep 0.01
    done
  ) &
  P32_BG_PID=$!
  set +e
  HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$P32_GUARD_REPO" --workspace-root "$P32_GUARD_WS" --global-state-root "$P32_GUARD_STATE" \
    --max-files 10 --max-seconds 1 --top-k 3 > /dev/null 2>&1
  P32_GUARD_RC=$?
  set -e
  wait "$P32_BG_PID" 2>/dev/null || true
  if [ "$P32_GUARD_RC" -eq 3 ]; then
    check "Phase32:read_only_guard_full_snapshot_ignores_limits" "PASS"
  else
    check "Phase32:read_only_guard_full_snapshot_ignores_limits" "FAIL"
  fi
else
  check "Phase32:scan_graph_schema_version_present" "FAIL"
  check "Phase32:scan_graph_strict_mismatch_reason_emitted" "FAIL"
  check "Phase32:discover_profile_diff_reuse_no_rescan" "FAIL"
  check "Phase32:machine_line_json_payload_additive" "FAIL"
  check "Phase32:governance_disabled_zero_write_still" "FAIL"
  check "Phase32:read_only_guard_full_snapshot_ignores_limits" "FAIL"
fi

# ─── Phase 33: machine-json roundtrip + deterministic ordering ───
echo "[phase 33] machine_json_roundtrip_and_determinism"
if [ -f "$PLUGIN" ] && [ -d "$CASE1" ] && [ -d "$CASE9" ]; then
  P33_WS="$REGRESSION_TMP/phase33_ws"
  P33_STATE="$REGRESSION_TMP/phase33_state"
  rm -rf "$P33_WS" "$P33_STATE"
  mkdir -p "$P33_WS" "$P33_STATE"

  # 1) machine_json_roundtrip_parse
  set +e
  P33_OUT_DISC=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --workspace-root "$P33_WS" --global-state-root "$P33_STATE" \
    --machine-json 1 --keywords notice 2>/dev/null)
  P33_RC_DISC=$?
  set -e
  P33_CAPS_LINE=$(printf '%s\n' "$P33_OUT_DISC" | grep '^HONGZHI_CAPS ' | head -n 1 || true)
  P33_JSON_OK=$("$PYTHON_BIN" - <<PY
import json, shlex
line = """$P33_CAPS_LINE"""
ok = False
try:
    tokens = shlex.split(line)
    payload = ""
    for tok in tokens:
        if tok.startswith("json="):
            payload = tok.split("=", 1)[1]
            break
    if payload:
        obj = json.loads(payload)
        ok = isinstance(obj, dict) and "path" in obj and "versions" in obj and "repo_fingerprint" in obj and "run_id" in obj
except Exception:
    ok = False
print("1" if ok else "0")
PY
)
  if [ "$P33_RC_DISC" -eq 0 ] && [ -n "$P33_CAPS_LINE" ] && [ "$P33_JSON_OK" = "1" ]; then
    check "Phase33:machine_json_roundtrip_parse" "PASS"
  else
    check "Phase33:machine_json_roundtrip_parse" "FAIL"
  fi

  # 2) machine_json_no_newlines
  P33_NO_NL_OK=$("$PYTHON_BIN" - <<PY
import shlex
line = """$P33_CAPS_LINE"""
ok = False
try:
    tokens = shlex.split(line)
    payload = ""
    for tok in tokens:
        if tok.startswith("json="):
            payload = tok.split("=", 1)[1]
            break
    ok = bool(payload) and ("\n" not in payload) and ("\r" not in payload)
except Exception:
    ok = False
print("1" if ok else "0")
PY
)
  if [ "$P33_NO_NL_OK" = "1" ]; then
    check "Phase33:machine_json_no_newlines" "PASS"
  else
    check "Phase33:machine_json_no_newlines" "FAIL"
  fi

  # 3) deterministic_artifacts_order
  P33_WS_D="$REGRESSION_TMP/phase33_ws_det"
  P33_STATE_D="$REGRESSION_TMP/phase33_state_det"
  rm -rf "$P33_WS_D" "$P33_STATE_D"
  mkdir -p "$P33_WS_D" "$P33_STATE_D"
  set +e
  P33_OUT_D1=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --workspace-root "$P33_WS_D" --global-state-root "$P33_STATE_D" \
    --machine-json 1 --keywords notice 2>/dev/null)
  P33_RC_D1=$?
  P33_OUT_D2=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --workspace-root "$P33_WS_D" --global-state-root "$P33_STATE_D" \
    --machine-json 1 --keywords notice 2>/dev/null)
  P33_RC_D2=$?
  set -e
  P33_CAP_D1=$(extract_machine_path "$(printf '%s\n' "$P33_OUT_D1" | grep '^HONGZHI_CAPS ' | head -n 1 || true)")
  P33_CAP_D2=$(extract_machine_path "$(printf '%s\n' "$P33_OUT_D2" | grep '^HONGZHI_CAPS ' | head -n 1 || true)")
  P33_ART_OK=$("$PYTHON_BIN" - <<PY
import json, pathlib
cap1 = pathlib.Path("$P33_CAP_D1")
cap2 = pathlib.Path("$P33_CAP_D2")
ok = False
if cap1.is_file() and cap2.is_file():
    d1 = json.loads(cap1.read_text(encoding="utf-8"))
    d2 = json.loads(cap2.read_text(encoding="utf-8"))
    def rel_artifacts(data, cap):
        out = []
        for ap in data.get("artifacts", []) if isinstance(data.get("artifacts"), list) else []:
            p = pathlib.Path(str(ap))
            try:
                out.append(str(p.resolve().relative_to(cap.parent.resolve())).replace("\\\\", "/"))
            except Exception:
                out.append(str(p))
        return out
    a1 = rel_artifacts(d1, cap1)
    a2 = rel_artifacts(d2, cap2)
    ok = a1 == a2
print("1" if ok else "0")
PY
)
  if [ "$P33_RC_D1" -eq 0 ] && [ "$P33_RC_D2" -eq 0 ] && [ "$P33_ART_OK" = "1" ]; then
    check "Phase33:deterministic_artifacts_order" "PASS"
  else
    check "Phase33:deterministic_artifacts_order" "FAIL"
  fi

  # 4) deterministic_modules_order (metrics.candidates)
  P33_MOD_OK=$("$PYTHON_BIN" - <<PY
import json, pathlib
cap1 = pathlib.Path("$P33_CAP_D1")
cap2 = pathlib.Path("$P33_CAP_D2")
ok = False
if cap1.is_file() and cap2.is_file():
    d1 = json.loads(cap1.read_text(encoding="utf-8"))
    d2 = json.loads(cap2.read_text(encoding="utf-8"))
    c1 = d1.get("metrics", {}).get("candidates", []) if isinstance(d1.get("metrics", {}), dict) else []
    c2 = d2.get("metrics", {}).get("candidates", []) if isinstance(d2.get("metrics", {}), dict) else []
    if isinstance(c1, list) and isinstance(c2, list):
        s1 = [(x.get("module_key",""), float(x.get("score",0) or 0.0)) for x in c1 if isinstance(x, dict)]
        s2 = [(x.get("module_key",""), float(x.get("score",0) or 0.0)) for x in c2 if isinstance(x, dict)]
        ordered = all(s1[i][1] >= s1[i+1][1] for i in range(len(s1)-1))
        ok = (s1 == s2) and ordered
print("1" if ok else "0")
PY
)
  if [ "$P33_MOD_OK" = "1" ]; then
    check "Phase33:deterministic_modules_order" "PASS"
  else
    check "Phase33:deterministic_modules_order" "FAIL"
  fi

  # 5) mismatch_reason enum + mismatch_suggestion
  P33_WS_M="$REGRESSION_TMP/phase33_ws_mismatch"
  P33_STATE_M="$REGRESSION_TMP/phase33_state_mismatch"
  rm -rf "$P33_WS_M" "$P33_STATE_M"
  mkdir -p "$P33_WS_M" "$P33_STATE_M"
  set +e
  P33_OUT_M=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE9" --workspace-root "$P33_WS_M" --global-state-root "$P33_STATE_M" \
    --machine-json 1 --strict --keywords weird 2>/dev/null)
  P33_RC_M=$?
  set -e
  P33_SUM_M=$(printf '%s\n' "$P33_OUT_M" | grep '^hongzhi_ai_kit_summary ' | head -n 1 || true)
  P33_MISMATCH_OK=$("$PYTHON_BIN" - <<PY
line = """$P33_SUM_M"""
ok = False
reason = ""
suggestion = ""
for tok in line.split():
    if tok.startswith("mismatch_reason="):
        reason = tok.split("=",1)[1]
    if tok.startswith("mismatch_suggestion="):
        suggestion = tok.split("=",1)[1]
allowed = {"schema_version_mismatch","producer_version_mismatch","fingerprint_mismatch","corrupted_cache","unknown"}
ok = (reason in allowed) and bool(suggestion and suggestion != "-")
print("1" if ok else "0")
PY
)
  if [ "$P33_RC_M" -eq 25 ] && echo "$P33_SUM_M" | grep -q 'exit_hint=scan_graph_mismatch' && [ "$P33_MISMATCH_OK" = "1" ]; then
    check "Phase33:mismatch_reason_enum_and_suggestion" "PASS"
  else
    check "Phase33:mismatch_reason_enum_and_suggestion" "FAIL"
  fi

  # 6) status/index never probe writable
  P33_WS_G="$REGRESSION_TMP/phase33_ws_gov"
  P33_STATE_G="$REGRESSION_TMP/phase33_state_gov"
  rm -rf "$P33_WS_G" "$P33_STATE_G"
  mkdir -p "$P33_WS_G" "$P33_STATE_G"
  P33_SIG_BEFORE=$(snapshot_sig "$P33_WS_G" "$P33_STATE_G")
  set +e
  unset HONGZHI_PLUGIN_ENABLE 2>/dev/null || true
  "$PYTHON_BIN" "$PLUGIN" status --repo-root "$CASE1" --workspace-root "$P33_WS_G" --global-state-root "$P33_STATE_G" --machine-json 1 > /dev/null 2>&1
  P33_RC_STATUS=$?
  "$PYTHON_BIN" "$PLUGIN" index list --global-state-root "$P33_STATE_G" --machine-json 1 > /dev/null 2>&1
  P33_RC_INDEX=$?
  set -e
  P33_SIG_AFTER=$(snapshot_sig "$P33_WS_G" "$P33_STATE_G")
  P33_PROBE_FILES=$(find "$P33_WS_G" "$P33_STATE_G" -type f \( -name ".write_test" -o -name "*.write_test" -o -name "*probe*" \) | wc -l | tr -d ' ')
  if [ "$P33_RC_STATUS" -eq 10 ] && [ "$P33_RC_INDEX" -eq 0 ] && [ "$P33_SIG_BEFORE" = "$P33_SIG_AFTER" ] && [ "$P33_PROBE_FILES" = "0" ]; then
    check "Phase33:status_index_never_probe_writable" "PASS"
  else
    check "Phase33:status_index_never_probe_writable" "FAIL"
  fi
else
  check "Phase33:machine_json_roundtrip_parse" "FAIL"
  check "Phase33:machine_json_no_newlines" "FAIL"
  check "Phase33:deterministic_artifacts_order" "FAIL"
  check "Phase33:deterministic_modules_order" "FAIL"
  check "Phase33:mismatch_reason_enum_and_suggestion" "FAIL"
  check "Phase33:status_index_never_probe_writable" "FAIL"
fi

# ─── Phase 34: machine-line contract schema + validator hard gate ───
echo "[phase 34] machine_line_contract_schema_validator_round28"
CONTRACT_SCHEMA_V1="$SCRIPT_DIR/contract_schema_v1.json"
CONTRACT_SCHEMA_V2="$SCRIPT_DIR/contract_schema_v2.json"
CONTRACT_VALIDATOR="$SCRIPT_DIR/contract_validator.py"
CONTRACT_SCHEMA_RUNTIME="$CONTRACT_SCHEMA_V1"
if [ -f "$CONTRACT_SCHEMA_V2" ]; then
  CONTRACT_SCHEMA_RUNTIME="$CONTRACT_SCHEMA_V2"
fi
if [ -f "$CONTRACT_SCHEMA_V1" ]; then
  set +e
  "$PYTHON_BIN" - <<PY
import json
import pathlib
path = pathlib.Path("$CONTRACT_SCHEMA_V1")
json.loads(path.read_text(encoding="utf-8"))
PY
  P34_SCHEMA_RC=$?
  set -e
  [ "$P34_SCHEMA_RC" -eq 0 ] && check "Phase34:contract_schema_v1_valid_json" "PASS" || check "Phase34:contract_schema_v1_valid_json" "FAIL"
else
  check "Phase34:contract_schema_v1_valid_json" "FAIL"
fi

if [ -f "$CONTRACT_SCHEMA_V2" ]; then
  set +e
  "$PYTHON_BIN" - <<PY
import json
import pathlib
path = pathlib.Path("$CONTRACT_SCHEMA_V2")
json.loads(path.read_text(encoding="utf-8"))
PY
  P34_SCHEMA_V2_RC=$?
  set -e
  [ "$P34_SCHEMA_V2_RC" -eq 0 ] && check "Phase34:contract_schema_v2_valid_json" "PASS" || check "Phase34:contract_schema_v2_valid_json" "FAIL"
else
  check "Phase34:contract_schema_v2_valid_json" "FAIL"
fi

if [ -f "$CONTRACT_VALIDATOR" ]; then
  set +e
  "$PYTHON_BIN" "$CONTRACT_VALIDATOR" --help > /dev/null 2>&1
  P34_HELP_RC=$?
  set -e
  [ "$P34_HELP_RC" -eq 0 ] && check "Phase34:contract_validator_smoke" "PASS" || check "Phase34:contract_validator_smoke" "FAIL"
else
  check "Phase34:contract_validator_smoke" "FAIL"
fi

if [ -f "$PLUGIN" ] && [ -f "$CONTRACT_SCHEMA_RUNTIME" ] && [ -f "$CONTRACT_VALIDATOR" ] && [ -d "$CASE1" ] && [ -d "$CASE9" ]; then
  P34_SCHEMA_ARGS=(--schema "$CONTRACT_SCHEMA_RUNTIME")
  if [ "$CONTRACT_SCHEMA_RUNTIME" = "$CONTRACT_SCHEMA_V2" ] && [ -f "$CONTRACT_SCHEMA_V1" ]; then
    P34_SCHEMA_ARGS+=(--baseline-schema "$CONTRACT_SCHEMA_V1")
  fi

  # 3) validator on discover stdout
  P34_WS_DISC="$REGRESSION_TMP/phase34_ws_discover"
  P34_STATE_DISC="$REGRESSION_TMP/phase34_state_discover"
  rm -rf "$P34_WS_DISC" "$P34_STATE_DISC"
  mkdir -p "$P34_WS_DISC" "$P34_STATE_DISC"
  set +e
  P34_OUT_DISC=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --workspace-root "$P34_WS_DISC" --global-state-root "$P34_STATE_DISC" \
    --machine-json 1 --keywords notice 2>/dev/null)
  P34_RC_DISC=$?
  set -e
  printf '%s\n' "$P34_OUT_DISC" > "$REGRESSION_TMP/phase34_discover_stdout.log"
  set +e
  printf '%s\n' "$P34_OUT_DISC" | "$PYTHON_BIN" "$CONTRACT_VALIDATOR" \
    "${P34_SCHEMA_ARGS[@]}" --stdin > "$REGRESSION_TMP/phase34_validator_discover.log" 2>&1
  P34_VAL_DISC_RC=$?
  set -e
  if [ "$P34_RC_DISC" -eq 0 ] && [ "$P34_VAL_DISC_RC" -eq 0 ] && grep -q '^CONTRACT_OK=1' "$REGRESSION_TMP/phase34_validator_discover.log"; then
    check "Phase34:contract_validator_on_discover_stdout" "PASS"
  else
    check "Phase34:contract_validator_on_discover_stdout" "FAIL"
  fi

  # 4) validator on governance block stdout (disabled => exit 10)
  P34_WS_GOV="$REGRESSION_TMP/phase34_ws_gov"
  P34_STATE_GOV="$REGRESSION_TMP/phase34_state_gov"
  rm -rf "$P34_WS_GOV" "$P34_STATE_GOV"
  mkdir -p "$P34_WS_GOV" "$P34_STATE_GOV"
  set +e
  unset HONGZHI_PLUGIN_ENABLE 2>/dev/null || true
  P34_OUT_GOV=$("$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --workspace-root "$P34_WS_GOV" --global-state-root "$P34_STATE_GOV" \
    --machine-json 1 2>/dev/null)
  P34_RC_GOV=$?
  set -e
  printf '%s\n' "$P34_OUT_GOV" > "$REGRESSION_TMP/phase34_gov_stdout.log"
  set +e
  printf '%s\n' "$P34_OUT_GOV" | "$PYTHON_BIN" "$CONTRACT_VALIDATOR" \
    "${P34_SCHEMA_ARGS[@]}" --stdin > "$REGRESSION_TMP/phase34_validator_gov.log" 2>&1
  P34_VAL_GOV_RC=$?
  set -e
  if [ "$P34_RC_GOV" -eq 10 ] && echo "$P34_OUT_GOV" | grep -q '^HONGZHI_GOV_BLOCK ' && \
     [ "$P34_VAL_GOV_RC" -eq 0 ] && grep -q '^CONTRACT_OK=1' "$REGRESSION_TMP/phase34_validator_gov.log"; then
    check "Phase34:contract_validator_on_gov_block_stdout" "PASS"
  else
    check "Phase34:contract_validator_on_gov_block_stdout" "FAIL"
  fi

  # 5) validator on strict mismatch stdout (exit 25)
  P34_WS_M="$REGRESSION_TMP/phase34_ws_mismatch"
  P34_STATE_M="$REGRESSION_TMP/phase34_state_mismatch"
  rm -rf "$P34_WS_M" "$P34_STATE_M"
  mkdir -p "$P34_WS_M" "$P34_STATE_M"
  set +e
  P34_OUT_M=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE9" --workspace-root "$P34_WS_M" --global-state-root "$P34_STATE_M" \
    --machine-json 1 --strict --keywords weird 2>/dev/null)
  P34_RC_M=$?
  set -e
  printf '%s\n' "$P34_OUT_M" > "$REGRESSION_TMP/phase34_mismatch_stdout.log"
  set +e
  printf '%s\n' "$P34_OUT_M" | "$PYTHON_BIN" "$CONTRACT_VALIDATOR" \
    "${P34_SCHEMA_ARGS[@]}" --stdin > "$REGRESSION_TMP/phase34_validator_mismatch.log" 2>&1
  P34_VAL_M_RC=$?
  set -e
  if [ "$P34_RC_M" -eq 25 ] && echo "$P34_OUT_M" | grep -q 'mismatch_reason=' && \
     [ "$P34_VAL_M_RC" -eq 0 ] && grep -q '^CONTRACT_OK=1' "$REGRESSION_TMP/phase34_validator_mismatch.log"; then
    check "Phase34:contract_validator_on_exit25_mismatch_stdout" "PASS"
  else
    check "Phase34:contract_validator_on_exit25_mismatch_stdout" "FAIL"
  fi

  # 6) schema additive guard (v2 should remain additive to v1)
  if [ -f "$CONTRACT_SCHEMA_V2" ] && [ -f "$CONTRACT_SCHEMA_V1" ]; then
    set +e
    "$PYTHON_BIN" "$CONTRACT_VALIDATOR" \
      --schema "$CONTRACT_SCHEMA_V2" \
      --baseline-schema "$CONTRACT_SCHEMA_V1" \
      --file "$REGRESSION_TMP/phase34_discover_stdout.log" > "$REGRESSION_TMP/phase34_validator_additive.log" 2>&1
    P34_VAL_ADD_RC=$?
    set -e
    if [ "$P34_VAL_ADD_RC" -eq 0 ] && grep -q '^CONTRACT_OK=1' "$REGRESSION_TMP/phase34_validator_additive.log"; then
      check "Phase34:contract_schema_v2_additive_guard_vs_v1" "PASS"
    else
      check "Phase34:contract_schema_v2_additive_guard_vs_v1" "FAIL"
    fi
  else
    check "Phase34:contract_schema_v2_additive_guard_vs_v1" "FAIL"
  fi
else
  check "Phase34:contract_validator_on_discover_stdout" "FAIL"
  check "Phase34:contract_validator_on_gov_block_stdout" "FAIL"
  check "Phase34:contract_validator_on_exit25_mismatch_stdout" "FAIL"
  check "Phase34:contract_schema_v2_additive_guard_vs_v1" "FAIL"
fi

# ─── Phase 35: company-scope gate + governance skills lifecycle ───
echo "[phase 35] company_scope_gate_and_skill_lifecycle_round29"
if [ -f "$PLUGIN" ] && [ -f "$SKILLS_JSON" ] && [ -d "$CASE1" ]; then
  # 1) Governance plugin skills should be deployed
  P35_SKILLS_OK=$("$PYTHON_BIN" - <<PY
import json
from pathlib import Path
p = Path("$SKILLS_JSON")
ok = False
try:
    data = json.loads(p.read_text(encoding="utf-8"))
    gov = [x for x in data if isinstance(x, dict) and str(x.get("name","")).startswith("skill_governance_plugin_")]
    ok = bool(gov) and all(str(x.get("status","")) == "deployed" for x in gov)
except Exception:
    ok = False
print("1" if ok else "0")
PY
)
  if [ "$P35_SKILLS_OK" = "1" ]; then
    check "Phase35:governance_skills_deployed" "PASS"
  else
    check "Phase35:governance_skills_deployed" "FAIL"
  fi

  # 2) machine lines should include company_scope token
  P35_WS_SCOPE="$REGRESSION_TMP/phase35_ws_scope"
  P35_STATE_SCOPE="$REGRESSION_TMP/phase35_state_scope"
  rm -rf "$P35_WS_SCOPE" "$P35_STATE_SCOPE"
  mkdir -p "$P35_WS_SCOPE" "$P35_STATE_SCOPE"
  set +e
  P35_OUT_DISC=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --workspace-root "$P35_WS_SCOPE" --global-state-root "$P35_STATE_SCOPE" \
    --machine-json 1 2>/dev/null)
  P35_RC_DISC=$?
  P35_OUT_STATUS=$(HONGZHI_PLUGIN_ENABLE=1 "$PYTHON_BIN" "$PLUGIN" status \
    --repo-root "$CASE1" --workspace-root "$P35_WS_SCOPE" --global-state-root "$P35_STATE_SCOPE" \
    --machine-json 1 2>/dev/null)
  P35_RC_STATUS=$?
  set -e
  if [ "$P35_RC_DISC" -eq 0 ] && [ "$P35_RC_STATUS" -eq 0 ] && \
     echo "$P35_OUT_DISC" | grep -q '^HONGZHI_CAPS ' && \
     echo "$P35_OUT_DISC" | grep -q 'company_scope=' && \
     echo "$P35_OUT_STATUS" | grep -q '^HONGZHI_STATUS ' && \
     echo "$P35_OUT_STATUS" | grep -q 'company_scope=' && \
     echo "$P35_OUT_DISC" | grep -q '^hongzhi_ai_kit_summary ' && \
     echo "$P35_OUT_DISC" | grep -q 'company_scope='; then
    check "Phase35:machine_lines_include_company_scope" "PASS"
  else
    check "Phase35:machine_lines_include_company_scope" "FAIL"
  fi

  # 3) default behavior: company-scope gate disabled unless explicitly required
  set +e
  P35_OUT_DEFAULT=$(HONGZHI_PLUGIN_ENABLE=1 HONGZHI_COMPANY_SCOPE=external-scope "$PYTHON_BIN" "$PLUGIN" status \
    --repo-root "$CASE1" --workspace-root "$P35_WS_SCOPE" --global-state-root "$P35_STATE_SCOPE" \
    --machine-json 1 2>/dev/null)
  P35_RC_DEFAULT=$?
  set -e
  if [ "$P35_RC_DEFAULT" -eq 0 ] && echo "$P35_OUT_DEFAULT" | grep -q '^HONGZHI_STATUS '; then
    check "Phase35:company_scope_gate_default_off" "PASS"
  else
    check "Phase35:company_scope_gate_default_off" "FAIL"
  fi

  # 4) required company-scope mismatch must block with exit 26
  P35_WS_BLOCK="$REGRESSION_TMP/phase35_ws_block"
  P35_STATE_BLOCK="$REGRESSION_TMP/phase35_state_block"
  rm -rf "$P35_WS_BLOCK" "$P35_STATE_BLOCK"
  mkdir -p "$P35_WS_BLOCK" "$P35_STATE_BLOCK"
  P35_SIG_BEFORE=$(snapshot_sig "$P35_WS_BLOCK" "$P35_STATE_BLOCK")
  set +e
  P35_OUT_BLOCK=$(HONGZHI_PLUGIN_ENABLE=1 HONGZHI_REQUIRE_COMPANY_SCOPE=1 HONGZHI_COMPANY_SCOPE=external-scope "$PYTHON_BIN" "$PLUGIN" discover \
    --repo-root "$CASE1" --workspace-root "$P35_WS_BLOCK" --global-state-root "$P35_STATE_BLOCK" \
    --machine-json 1 2>/dev/null)
  P35_RC_BLOCK=$?
  set -e
  P35_SIG_AFTER=$(snapshot_sig "$P35_WS_BLOCK" "$P35_STATE_BLOCK")
  if [ "$P35_RC_BLOCK" -eq 26 ] && \
     echo "$P35_OUT_BLOCK" | grep -q '^HONGZHI_GOV_BLOCK ' && \
     echo "$P35_OUT_BLOCK" | grep -q 'reason=company_scope_mismatch'; then
    check "Phase35:company_scope_mismatch_block_exit26" "PASS"
  else
    check "Phase35:company_scope_mismatch_block_exit26" "FAIL"
  fi

  # 5) scope mismatch block must remain zero-write
  if [ "$P35_SIG_BEFORE" = "$P35_SIG_AFTER" ]; then
    check "Phase35:company_scope_mismatch_zero_write" "PASS"
  else
    check "Phase35:company_scope_mismatch_zero_write" "FAIL"
  fi

  # 6) required scope match should allow execution
  set +e
  P35_OUT_MATCH=$(HONGZHI_PLUGIN_ENABLE=1 HONGZHI_REQUIRE_COMPANY_SCOPE=1 HONGZHI_COMPANY_SCOPE=hongzhi-work-dev "$PYTHON_BIN" "$PLUGIN" status \
    --repo-root "$CASE1" --workspace-root "$P35_WS_SCOPE" --global-state-root "$P35_STATE_SCOPE" \
    --machine-json 1 2>/dev/null)
  P35_RC_MATCH=$?
  set -e
  if [ "$P35_RC_MATCH" -eq 0 ] && echo "$P35_OUT_MATCH" | grep -q '^HONGZHI_STATUS ' && \
     echo "$P35_OUT_MATCH" | grep -q 'company_scope='; then
    check "Phase35:company_scope_match_required_allows" "PASS"
  else
    check "Phase35:company_scope_match_required_allows" "FAIL"
  fi
else
  check "Phase35:governance_skills_deployed" "FAIL"
  check "Phase35:machine_lines_include_company_scope" "FAIL"
  check "Phase35:company_scope_gate_default_off" "FAIL"
  check "Phase35:company_scope_mismatch_block_exit26" "FAIL"
  check "Phase35:company_scope_mismatch_zero_write" "FAIL"
  check "Phase35:company_scope_match_required_allows" "FAIL"
fi

# ─── Phase 36: strict self-upgrade chain + contract sample replay + A3 templates ───
echo "[phase 36] strict_self_upgrade_and_contract_replay_round30"
RUN_WRAPPER="$SCRIPT_DIR/run.sh"
CONTRACT_REPLAY="$SCRIPT_DIR/contract_samples/replay_contract_samples.sh"
A3_TEMPLATE_DIR="$REPO_ROOT/prompt-dsl-system/tools/artifacts/templates/kit_self_upgrade"
if [ -f "$RUN_WRAPPER" ] && [ -d "$REPO_ROOT/prompt-dsl-system" ]; then
  P36_REPO="$REGRESSION_TMP/phase36_repo"
  rm -rf "$P36_REPO"
  mkdir -p "$P36_REPO"
  cp -R "$REPO_ROOT/prompt-dsl-system" "$P36_REPO/"
  if [ -f "$REPO_ROOT/README.md" ]; then
    cp "$REPO_ROOT/README.md" "$P36_REPO/README.md"
  fi
  if [ -f "$REPO_ROOT/.github/workflows/kit_guardrails.yml" ]; then
    mkdir -p "$P36_REPO/.github/workflows"
    cp "$REPO_ROOT/.github/workflows/kit_guardrails.yml" "$P36_REPO/.github/workflows/kit_guardrails.yml"
  fi
  (
    cd "$P36_REPO"
    git init -q >/dev/null 2>&1 || true
    git config user.email "regression@example.com" >/dev/null 2>&1 || true
    git config user.name "Regression Bot" >/dev/null 2>&1 || true
  )

  set +e
  P36_OUT=$(bash "$RUN_WRAPPER" self-upgrade -r "$P36_REPO" --strict-self-upgrade 2>/dev/null)
  P36_RC=$?
  set -e
  printf '%s\n' "$P36_OUT" > "$REGRESSION_TMP/phase36_self_upgrade.log"
  if [ "$P36_RC" -eq 0 ] && \
     echo "$P36_OUT" | grep -q 'cmd_alias=self-upgrade->run' && \
     echo "$P36_OUT" | grep -q '\[hongzhi\]\[self-upgrade\]\[strict\] preflight PASS' && \
     echo "$P36_OUT" | grep -q '\[selfcheck_gate\] PASS' && \
     echo "$P36_OUT" | grep -q '^CONTRACT_OK=1 '; then
    check "Phase36:self_upgrade_strict_preflight_on_temp_repo" "PASS"
  else
    check "Phase36:self_upgrade_strict_preflight_on_temp_repo" "FAIL"
  fi
else
  check "Phase36:self_upgrade_strict_preflight_on_temp_repo" "FAIL"
fi

if [ -f "$CONTRACT_REPLAY" ]; then
  set +e
  bash "$CONTRACT_REPLAY" --repo-root "$REPO_ROOT" > "$REGRESSION_TMP/phase36_contract_replay.log" 2>&1
  P36_REPLAY_RC=$?
  set -e
  if [ "$P36_REPLAY_RC" -eq 0 ]; then
    check "Phase36:contract_sample_replay_v2" "PASS"
  else
    check "Phase36:contract_sample_replay_v2" "FAIL"
  fi
else
  check "Phase36:contract_sample_replay_v2" "FAIL"
fi

if [ -f "$A3_TEMPLATE_DIR/A3_change_ledger.template.md" ] && \
   [ -f "$A3_TEMPLATE_DIR/A3_rollback_plan.template.md" ] && \
   [ -f "$A3_TEMPLATE_DIR/A3_cleanup_report.template.md" ]; then
  check "Phase36:a3_kit_self_upgrade_templates_exist" "PASS"
else
  check "Phase36:a3_kit_self_upgrade_templates_exist" "FAIL"
fi

# ─── Phase 37: validate default post-gates (contract replay + template guard) ───
echo "[phase 37] validate_default_post_gates_round31"
if [ -f "$RUN_WRAPPER" ] && [ -d "$REPO_ROOT/prompt-dsl-system" ]; then
  P37_REPO="$REGRESSION_TMP/phase37_repo"
  rm -rf "$P37_REPO"
  mkdir -p "$P37_REPO"
  cp -R "$REPO_ROOT/prompt-dsl-system" "$P37_REPO/"
  if [ -f "$REPO_ROOT/README.md" ]; then
    cp "$REPO_ROOT/README.md" "$P37_REPO/README.md"
  fi
  if [ -d "$REPO_ROOT/.github" ]; then
    cp -R "$REPO_ROOT/.github" "$P37_REPO/.github"
  fi
  (
    cd "$P37_REPO"
    git init -q >/dev/null 2>&1 || true
    git config user.email "regression@example.com" >/dev/null 2>&1 || true
    git config user.name "Regression Bot" >/dev/null 2>&1 || true
  )

  set +e
  P37_OUT=$(bash "$RUN_WRAPPER" validate -r "$P37_REPO" -m "$P37_REPO" 2>/dev/null)
  P37_RC=$?
  set -e
  printf '%s\n' "$P37_OUT" > "$REGRESSION_TMP/phase37_validate.log"

  if [ "$P37_RC" -eq 0 ] && echo "$P37_OUT" | grep -q '\[contract_replay\] PASS'; then
    check "Phase37:validate_runs_contract_sample_replay" "PASS"
  else
    check "Phase37:validate_runs_contract_sample_replay" "FAIL"
  fi

  if [ "$P37_RC" -eq 0 ] && echo "$P37_OUT" | grep -q '\[template_guard\] PASS'; then
    check "Phase37:validate_runs_template_guard" "PASS"
  else
    check "Phase37:validate_runs_template_guard" "FAIL"
  fi
else
  check "Phase37:validate_runs_contract_sample_replay" "FAIL"
  check "Phase37:validate_runs_template_guard" "FAIL"
fi

# ─── Phase 38: health report post-validate gates section ───
echo "[phase 38] health_report_post_validate_section_round32"
if [ -n "${P37_REPO:-}" ] && [ -f "$P37_REPO/prompt-dsl-system/tools/health_report.json" ] && [ -f "$P37_REPO/prompt-dsl-system/tools/health_report.md" ]; then
  P38_JSON_OK=$("$PYTHON_BIN" - <<PY
import json
from pathlib import Path
p = Path("$P37_REPO/prompt-dsl-system/tools/health_report.json")
ok = False
try:
    d = json.loads(p.read_text(encoding="utf-8"))
    section = d.get("post_validate_gates")
    if isinstance(section, dict):
        gates = section.get("gates")
        gate_map = {str(x.get("name")): str(x.get("status")) for x in gates if isinstance(x, dict)} if isinstance(gates, list) else {}
        ok = gate_map.get("contract_sample_replay") == "PASS" and gate_map.get("kit_template_guard") == "PASS"
except Exception:
    ok = False
print("1" if ok else "0")
PY
)
  if [ "$P38_JSON_OK" = "1" ]; then
    check "Phase38:health_report_json_has_post_validate_gates" "PASS"
  else
    check "Phase38:health_report_json_has_post_validate_gates" "FAIL"
  fi

  if grep -q "## Post-Validate Gates" "$P37_REPO/prompt-dsl-system/tools/health_report.md" && \
     grep -q "<!-- POST_VALIDATE_GATES_START -->" "$P37_REPO/prompt-dsl-system/tools/health_report.md" && \
     grep -q "<!-- POST_VALIDATE_GATES_END -->" "$P37_REPO/prompt-dsl-system/tools/health_report.md"; then
    check "Phase38:health_report_md_has_post_validate_section" "PASS"
  else
    check "Phase38:health_report_md_has_post_validate_section" "FAIL"
  fi
else
  check "Phase38:health_report_json_has_post_validate_gates" "FAIL"
  check "Phase38:health_report_md_has_post_validate_section" "FAIL"
fi

# ─── Phase 39: health_runbook fail-first on post-validate gates ───
echo "[phase 39] health_runbook_post_gate_fail_first_round33"
HEALTH_RUNBOOK_GEN="$SCRIPT_DIR/health_runbook_generator.py"
if [ -f "$HEALTH_RUNBOOK_GEN" ] && [ -n "${P37_REPO:-}" ]; then
  P39_REPORT_IN="$P37_REPO/prompt-dsl-system/tools/health_report.json"
  P39_REPORT_FAIL="$REGRESSION_TMP/phase39_health_report_fail.json"
  P39_OUT_DIR="$REGRESSION_TMP/phase39_runbook"
  rm -rf "$P39_OUT_DIR"
  mkdir -p "$P39_OUT_DIR"

  if [ -f "$P39_REPORT_IN" ]; then
    "$PYTHON_BIN" - <<PY
import json
from pathlib import Path
src = Path("$P39_REPORT_IN")
dst = Path("$P39_REPORT_FAIL")
data = json.loads(src.read_text(encoding="utf-8"))
section = data.get("post_validate_gates")
if not isinstance(section, dict):
    section = {}
section["overall_status"] = "FAIL"
gates = section.get("gates")
if not isinstance(gates, list):
    gates = []
gate_map = {str(x.get("name")): x for x in gates if isinstance(x, dict)}
for name in ("contract_sample_replay", "kit_template_guard"):
    if name not in gate_map:
        gates.append({"name": name, "status": "FAIL", "exit_code": 2})
    else:
        gate_map[name]["status"] = "FAIL"
        gate_map[name]["exit_code"] = 2
section["gates"] = gates
data["post_validate_gates"] = section
dst.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
PY

    set +e
    "$PYTHON_BIN" "$HEALTH_RUNBOOK_GEN" \
      --repo-root "$P37_REPO" \
      --health-report "$P39_REPORT_FAIL" \
      --output-dir "$P39_OUT_DIR" > "$REGRESSION_TMP/phase39_runbook.log" 2>&1
    P39_RC=$?
    set -e
    if [ "$P39_RC" -eq 0 ] && [ -f "$P39_OUT_DIR/health_runbook.json" ]; then
      check "Phase39:runbook_generated_on_post_gate_fail" "PASS"
    else
      check "Phase39:runbook_generated_on_post_gate_fail" "FAIL"
    fi

    P39_FIRST_STEP_OK=$("$PYTHON_BIN" - <<PY
import json
from pathlib import Path
p = Path("$P39_OUT_DIR/health_runbook.json")
ok = False
try:
    data = json.loads(p.read_text(encoding="utf-8"))
    steps = data.get("steps")
    ctx = data.get("decision_context", {})
    if isinstance(steps, list) and steps:
        first = steps[0]
        title = str(first.get("title", ""))
        cmd = str(first.get("command", ""))
        ok = title.startswith("Post-Gate Block: Re-run Validate") and "./prompt-dsl-system/tools/run.sh validate" in cmd and str(ctx.get("post_validate_overall_status", "")).upper() == "FAIL"
except Exception:
    ok = False
print("1" if ok else "0")
PY
)
    if [ "$P39_FIRST_STEP_OK" = "1" ]; then
      check "Phase39:runbook_post_gate_fail_first_block" "PASS"
    else
      check "Phase39:runbook_post_gate_fail_first_block" "FAIL"
    fi
  else
    check "Phase39:runbook_generated_on_post_gate_fail" "FAIL"
    check "Phase39:runbook_post_gate_fail_first_block" "FAIL"
  fi
else
  check "Phase39:runbook_generated_on_post_gate_fail" "FAIL"
  check "Phase39:runbook_post_gate_fail_first_block" "FAIL"
fi

# ─── Phase 40: selfcheck quality gate strict threshold ───
echo "[phase 40] selfcheck_quality_gate_round34"
SELFCHECK_GATE="$SCRIPT_DIR/kit_selfcheck_gate.py"
if [ -f "$SELFCHECK_GATE" ]; then
  P40_LOW="$REGRESSION_TMP/phase40_selfcheck_low.json"
  cat > "$P40_LOW" <<'JSON'
{
  "summary": {
    "overall_score": 0.72,
    "overall_level": "medium",
    "dimension_count": 2
  },
  "dimensions": {
    "generality": {"score": 1.0, "level": "high"},
    "robustness": {"score": 0.5, "level": "low"}
  },
  "recommendations": [
    "robustness: add missing guard artifacts."
  ]
}
JSON

  set +e
  P40_OUT_LOW=$("$PYTHON_BIN" "$SELFCHECK_GATE" \
    --report-json "$P40_LOW" \
    --min-overall-score 0.85 \
    --min-overall-level high \
    --max-low-dimensions 0 2>/dev/null)
  P40_LOW_RC=$?
  set -e
  printf '%s\n' "$P40_OUT_LOW" > "$REGRESSION_TMP/phase40_gate_low.log"
  if [ "$P40_LOW_RC" -ne 0 ] && echo "$P40_OUT_LOW" | grep -q '\[selfcheck_gate\] FAIL'; then
    check "Phase40:selfcheck_gate_blocks_low_quality_report" "PASS"
  else
    check "Phase40:selfcheck_gate_blocks_low_quality_report" "FAIL"
  fi

  P40_HIGH="$REGRESSION_TMP/phase40_selfcheck_high.json"
  cat > "$P40_HIGH" <<'JSON'
{
  "summary": {
    "overall_score": 0.95,
    "overall_level": "high",
    "dimension_count": 7
  },
  "dimensions": {
    "generality": {"score": 1.0, "level": "high"},
    "completeness": {"score": 0.9, "level": "high"},
    "robustness": {"score": 0.9, "level": "high"},
    "efficiency": {"score": 0.9, "level": "high"},
    "extensibility": {"score": 0.9, "level": "high"},
    "security_governance": {"score": 0.9, "level": "high"},
    "kit_mainline_focus": {"score": 0.9, "level": "high"}
  }
}
JSON

  set +e
  P40_OUT_HIGH=$("$PYTHON_BIN" "$SELFCHECK_GATE" \
    --report-json "$P40_HIGH" \
    --min-overall-score 0.85 \
    --min-overall-level high \
    --max-low-dimensions 0 2>/dev/null)
  P40_HIGH_RC=$?
  set -e
  printf '%s\n' "$P40_OUT_HIGH" > "$REGRESSION_TMP/phase40_gate_high.log"
  if [ "$P40_HIGH_RC" -eq 0 ] && echo "$P40_OUT_HIGH" | grep -q '\[selfcheck_gate\] PASS'; then
    check "Phase40:selfcheck_gate_accepts_high_quality_report" "PASS"
  else
    check "Phase40:selfcheck_gate_accepts_high_quality_report" "FAIL"
  fi
else
  check "Phase40:selfcheck_gate_blocks_low_quality_report" "FAIL"
  check "Phase40:selfcheck_gate_accepts_high_quality_report" "FAIL"
fi

fi

if [ "$RUN_LATE" = "true" ]; then
# ─── Phase 41: selfcheck required dimensions + summary count contract ───
echo "[phase 41] selfcheck_dimension_contract_round35"
SELFCHECK_GATE="$SCRIPT_DIR/kit_selfcheck_gate.py"
if [ -f "$SELFCHECK_GATE" ]; then
  P41_MISSING="$REGRESSION_TMP/phase41_selfcheck_missing_required.json"
  cat > "$P41_MISSING" <<'JSON'
{
  "summary": {
    "overall_score": 0.95,
    "overall_level": "high",
    "dimension_count": 6
  },
  "dimensions": {
    "generality": {"score": 1.0, "level": "high"},
    "completeness": {"score": 0.9, "level": "high"},
    "robustness": {"score": 0.9, "level": "high"},
    "efficiency": {"score": 0.9, "level": "high"},
    "extensibility": {"score": 0.9, "level": "high"},
    "security_governance": {"score": 0.9, "level": "high"}
  }
}
JSON

  set +e
  P41_OUT_MISSING=$("$PYTHON_BIN" "$SELFCHECK_GATE" \
    --report-json "$P41_MISSING" \
    --min-overall-score 0.85 \
    --min-overall-level high \
    --max-low-dimensions 0 2>/dev/null)
  P41_MISSING_RC=$?
  set -e
  printf '%s\n' "$P41_OUT_MISSING" > "$REGRESSION_TMP/phase41_gate_missing.log"
  if [ "$P41_MISSING_RC" -ne 0 ] && echo "$P41_OUT_MISSING" | grep -q 'required dimensions missing'; then
    check "Phase41:selfcheck_gate_blocks_missing_required_dimensions" "PASS"
  else
    check "Phase41:selfcheck_gate_blocks_missing_required_dimensions" "FAIL"
  fi

  P41_COUNT_MISMATCH="$REGRESSION_TMP/phase41_selfcheck_count_mismatch.json"
  cat > "$P41_COUNT_MISMATCH" <<'JSON'
{
  "summary": {
    "overall_score": 0.95,
    "overall_level": "high",
    "dimension_count": 6
  },
  "dimensions": {
    "generality": {"score": 1.0, "level": "high"},
    "completeness": {"score": 0.9, "level": "high"},
    "robustness": {"score": 0.9, "level": "high"},
    "efficiency": {"score": 0.9, "level": "high"},
    "extensibility": {"score": 0.9, "level": "high"},
    "security_governance": {"score": 0.9, "level": "high"},
    "kit_mainline_focus": {"score": 0.9, "level": "high"}
  }
}
JSON

  set +e
  P41_OUT_COUNT=$("$PYTHON_BIN" "$SELFCHECK_GATE" \
    --report-json "$P41_COUNT_MISMATCH" \
    --min-overall-score 0.85 \
    --min-overall-level high \
    --max-low-dimensions 0 2>/dev/null)
  P41_COUNT_RC=$?
  set -e
  printf '%s\n' "$P41_OUT_COUNT" > "$REGRESSION_TMP/phase41_gate_count.log"
  if [ "$P41_COUNT_RC" -ne 0 ] && echo "$P41_OUT_COUNT" | grep -q 'summary.dimension_count mismatch'; then
    check "Phase41:selfcheck_gate_blocks_dimension_count_mismatch" "PASS"
  else
    check "Phase41:selfcheck_gate_blocks_dimension_count_mismatch" "FAIL"
  fi
else
  check "Phase41:selfcheck_gate_blocks_missing_required_dimensions" "FAIL"
  check "Phase41:selfcheck_gate_blocks_dimension_count_mismatch" "FAIL"
fi

# ─── Phase 42: selfcheck freshness + git snapshot consistency ───
echo "[phase 42] selfcheck_freshness_gate_round36"
SELFCHECK_FRESHNESS="$SCRIPT_DIR/kit_selfcheck_freshness_gate.py"
SELFCHECK_SCRIPT="$SCRIPT_DIR/kit_selfcheck.py"
if [ -f "$SELFCHECK_FRESHNESS" ] && [ -f "$SELFCHECK_SCRIPT" ]; then
  P42_STALE="$REGRESSION_TMP/phase42_selfcheck_stale.json"
  "$PYTHON_BIN" - "$P42_STALE" "$REPO_ROOT" <<'PY'
import json
import pathlib
import subprocess
import sys

out_path = pathlib.Path(sys.argv[1])
repo_root = pathlib.Path(sys.argv[2]).resolve()
head = ""
head_available = False
try:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--verify", "HEAD"],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        head = proc.stdout.strip()
        head_available = bool(head)
except OSError:
    pass

payload = {
    "tool": "kit_selfcheck",
    "tool_version": "1.0.0",
    "generated_at": "2000-01-01T00:00:00Z",
    "repo_root": str(repo_root),
    "repo_snapshot": {
        "git_head": head,
        "git_head_available": head_available,
        "git_dirty": False,
    },
    "summary": {
        "overall_score": 0.9,
        "overall_level": "high",
        "dimension_count": 1,
    },
    "dimensions": {
        "generality": {
            "score": 0.9,
            "level": "high",
            "missing": [],
        }
    },
}
out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
  set +e
  P42_OUT_STALE=$("$PYTHON_BIN" "$SELFCHECK_FRESHNESS" \
    --report-json "$P42_STALE" \
    --repo-root "$REPO_ROOT" \
    --max-age-seconds 60 \
    --require-git-head false 2>/dev/null)
  P42_STALE_RC=$?
  set -e
  printf '%s\n' "$P42_OUT_STALE" > "$REGRESSION_TMP/phase42_freshness_stale.log"
  if [ "$P42_STALE_RC" -ne 0 ] && echo "$P42_OUT_STALE" | grep -q 'report is stale'; then
    check "Phase42:selfcheck_freshness_blocks_stale_report" "PASS"
  else
    check "Phase42:selfcheck_freshness_blocks_stale_report" "FAIL"
  fi

  P42_FRESH_JSON="$REGRESSION_TMP/phase42_selfcheck_fresh.json"
  P42_FRESH_MD="$REGRESSION_TMP/phase42_selfcheck_fresh.md"
  "$PYTHON_BIN" "$SELFCHECK_SCRIPT" \
    --repo-root "$REPO_ROOT" \
    --out-json "$P42_FRESH_JSON" \
    --out-md "$P42_FRESH_MD" >/dev/null 2>&1
  set +e
  P42_OUT_FRESH=$("$PYTHON_BIN" "$SELFCHECK_FRESHNESS" \
    --report-json "$P42_FRESH_JSON" \
    --repo-root "$REPO_ROOT" \
    --max-age-seconds 600 \
    --require-git-head false 2>/dev/null)
  P42_FRESH_RC=$?
  set -e
  printf '%s\n' "$P42_OUT_FRESH" > "$REGRESSION_TMP/phase42_freshness_fresh.log"
  if [ "$P42_FRESH_RC" -eq 0 ] && echo "$P42_OUT_FRESH" | grep -q '\[selfcheck_freshness\] PASS'; then
    check "Phase42:selfcheck_freshness_accepts_fresh_report" "PASS"
  else
    check "Phase42:selfcheck_freshness_accepts_fresh_report" "FAIL"
  fi
else
  check "Phase42:selfcheck_freshness_blocks_stale_report" "FAIL"
  check "Phase42:selfcheck_freshness_accepts_fresh_report" "FAIL"
fi

# ─── Phase 43: kit integrity manifest gate ───
echo "[phase 43] kit_integrity_gate_round37"
KIT_INTEGRITY="$SCRIPT_DIR/kit_integrity_guard.py"
P43_MANIFEST="$REPO_ROOT/prompt-dsl-system/tools/kit_integrity_manifest.json"
if [ -f "$KIT_INTEGRITY" ] && [ -f "$P43_MANIFEST" ]; then
  set +e
  P43_OUT_PASS=$("$PYTHON_BIN" "$KIT_INTEGRITY" verify \
    --repo-root "$REPO_ROOT" \
    --manifest "$P43_MANIFEST" \
    --strict-source-set true 2>/dev/null)
  P43_PASS_RC=$?
  set -e
  printf '%s\n' "$P43_OUT_PASS" > "$REGRESSION_TMP/phase43_integrity_pass.log"
  if [ "$P43_PASS_RC" -eq 0 ] && echo "$P43_OUT_PASS" | grep -q '\[kit_integrity\] PASS'; then
    check "Phase43:kit_integrity_accepts_manifest_baseline" "PASS"
  else
    check "Phase43:kit_integrity_accepts_manifest_baseline" "FAIL"
  fi

  P43_BAD_MANIFEST="$REGRESSION_TMP/phase43_integrity_bad_manifest.json"
  cp "$P43_MANIFEST" "$P43_BAD_MANIFEST"
  "$PYTHON_BIN" - "$P43_BAD_MANIFEST" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
entries = data.get("entries")
if isinstance(entries, list) and entries and isinstance(entries[0], dict):
    entries[0]["sha256"] = "0" * 64
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
  set +e
  P43_OUT_FAIL=$("$PYTHON_BIN" "$KIT_INTEGRITY" verify \
    --repo-root "$REPO_ROOT" \
    --manifest "$P43_BAD_MANIFEST" \
    --strict-source-set true 2>/dev/null)
  P43_FAIL_RC=$?
  set -e
  printf '%s\n' "$P43_OUT_FAIL" > "$REGRESSION_TMP/phase43_integrity_fail.log"
  if [ "$P43_FAIL_RC" -ne 0 ] && echo "$P43_OUT_FAIL" | grep -q 'sha256 mismatch'; then
    check "Phase43:kit_integrity_detects_hash_mismatch" "PASS"
  else
    check "Phase43:kit_integrity_detects_hash_mismatch" "FAIL"
  fi
else
  check "Phase43:kit_integrity_accepts_manifest_baseline" "FAIL"
  check "Phase43:kit_integrity_detects_hash_mismatch" "FAIL"
fi

# ─── Phase 44: pipeline trust whitelist gate ───
echo "[phase 44] pipeline_trust_gate_round38"
PIPELINE_TRUST="$SCRIPT_DIR/pipeline_trust_guard.py"
PIPELINE_RUNNER="$SCRIPT_DIR/pipeline_runner.py"
P44_WHITELIST="$REPO_ROOT/prompt-dsl-system/tools/pipeline_trust_whitelist.json"
P44_PIPELINE_REL="prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_kit_self_upgrade.md"
P44_PIPELINE_ABS="$REPO_ROOT/$P44_PIPELINE_REL"
if [ -f "$PIPELINE_TRUST" ] && [ -f "$PIPELINE_RUNNER" ] && [ -f "$P44_WHITELIST" ] && [ -f "$P44_PIPELINE_ABS" ]; then
  set +e
  P44_OUT_PASS=$("$PYTHON_BIN" "$PIPELINE_TRUST" verify \
    --repo-root "$REPO_ROOT" \
    --pipeline "$P44_PIPELINE_ABS" \
    --whitelist "$P44_WHITELIST" \
    --strict-source-set true \
    --require-active true 2>/dev/null)
  P44_PASS_RC=$?
  set -e
  printf '%s\n' "$P44_OUT_PASS" > "$REGRESSION_TMP/phase44_trust_pass.log"
  if [ "$P44_PASS_RC" -eq 0 ] && echo "$P44_OUT_PASS" | grep -q '\[pipeline_trust\] PASS'; then
    check "Phase44:pipeline_trust_accepts_whitelist_baseline" "PASS"
  else
    check "Phase44:pipeline_trust_accepts_whitelist_baseline" "FAIL"
  fi

  P44_BAD_WHITELIST="$REGRESSION_TMP/phase44_pipeline_trust_bad_whitelist.json"
  cp "$P44_WHITELIST" "$P44_BAD_WHITELIST"
  "$PYTHON_BIN" - "$P44_BAD_WHITELIST" "$P44_PIPELINE_REL" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
target = sys.argv[2]
data = json.loads(path.read_text(encoding="utf-8"))
entries = data.get("entries")
if isinstance(entries, list):
    for item in entries:
        if isinstance(item, dict) and str(item.get("path", "")) == target:
            item["sha256"] = "f" * 64
            break
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
  set +e
  P44_OUT_FAIL=$("$PYTHON_BIN" "$PIPELINE_TRUST" verify \
    --repo-root "$REPO_ROOT" \
    --pipeline "$P44_PIPELINE_ABS" \
    --whitelist "$P44_BAD_WHITELIST" \
    --strict-source-set true \
    --require-active true 2>/dev/null)
  P44_FAIL_RC=$?
  set -e
  printf '%s\n' "$P44_OUT_FAIL" > "$REGRESSION_TMP/phase44_trust_fail.log"
  if [ "$P44_FAIL_RC" -ne 0 ] && echo "$P44_OUT_FAIL" | grep -q 'sha256 mismatch'; then
    check "Phase44:pipeline_trust_detects_hash_mismatch" "PASS"
  else
    check "Phase44:pipeline_trust_detects_hash_mismatch" "FAIL"
  fi

  set +e
  P44_RUN_OUT=$(HONGZHI_PIPELINE_TRUST_WHITELIST="$P44_BAD_WHITELIST" \
    "$PYTHON_BIN" "$PIPELINE_RUNNER" run \
      --repo-root "$REPO_ROOT" \
      --module-path "$REPO_ROOT/prompt-dsl-system" \
      --pipeline "$P44_PIPELINE_REL" 2>/dev/null)
  P44_RUN_RC=$?
  set -e
  printf '%s\n' "$P44_RUN_OUT" > "$REGRESSION_TMP/phase44_runner_block.log"
  if [ "$P44_RUN_RC" -ne 0 ] && echo "$P44_RUN_OUT" | grep -q '\[pipeline_trust\] FAIL'; then
    check "Phase44:pipeline_runner_blocks_untrusted_pipeline" "PASS"
  else
    check "Phase44:pipeline_runner_blocks_untrusted_pipeline" "FAIL"
  fi
else
  check "Phase44:pipeline_trust_accepts_whitelist_baseline" "FAIL"
  check "Phase44:pipeline_trust_detects_hash_mismatch" "FAIL"
  check "Phase44:pipeline_runner_blocks_untrusted_pipeline" "FAIL"
fi

# ─── Phase 45: baseline signature guard (manifest + whitelist) ───
echo "[phase 45] baseline_signature_guard_round39"
KIT_INTEGRITY="$SCRIPT_DIR/kit_integrity_guard.py"
PIPELINE_TRUST="$SCRIPT_DIR/pipeline_trust_guard.py"
P45_MANIFEST="$REPO_ROOT/prompt-dsl-system/tools/kit_integrity_manifest.json"
P45_WHITELIST="$REPO_ROOT/prompt-dsl-system/tools/pipeline_trust_whitelist.json"
P45_PIPELINE_REL="prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_kit_self_upgrade.md"
P45_PIPELINE_ABS="$REPO_ROOT/$P45_PIPELINE_REL"
if [ -f "$KIT_INTEGRITY" ] && [ -f "$PIPELINE_TRUST" ] && [ -f "$P45_MANIFEST" ] && [ -f "$P45_WHITELIST" ]; then
  P45_BAD_MANIFEST="$REGRESSION_TMP/phase45_bad_manifest_signature.json"
  cp "$P45_MANIFEST" "$P45_BAD_MANIFEST"
  "$PYTHON_BIN" - "$P45_BAD_MANIFEST" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
sig = data.get("signature")
if isinstance(sig, dict):
    sig["content_sha256"] = "0" * 64
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
  set +e
  P45_OUT_MANIFEST=$("$PYTHON_BIN" "$KIT_INTEGRITY" verify \
    --repo-root "$REPO_ROOT" \
    --manifest "$P45_BAD_MANIFEST" \
    --strict-source-set true 2>/dev/null)
  P45_MANIFEST_RC=$?
  set -e
  printf '%s\n' "$P45_OUT_MANIFEST" > "$REGRESSION_TMP/phase45_manifest_signature.log"
  if [ "$P45_MANIFEST_RC" -ne 0 ] && echo "$P45_OUT_MANIFEST" | grep -q 'signature content_sha256 mismatch'; then
    check "Phase45:kit_integrity_detects_signature_mismatch" "PASS"
  else
    check "Phase45:kit_integrity_detects_signature_mismatch" "FAIL"
  fi

  P45_BAD_WHITELIST="$REGRESSION_TMP/phase45_bad_whitelist_signature.json"
  cp "$P45_WHITELIST" "$P45_BAD_WHITELIST"
  "$PYTHON_BIN" - "$P45_BAD_WHITELIST" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
sig = data.get("signature")
if isinstance(sig, dict):
    sig["content_sha256"] = "f" * 64
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
  set +e
  P45_OUT_WHITELIST=$("$PYTHON_BIN" "$PIPELINE_TRUST" verify \
    --repo-root "$REPO_ROOT" \
    --pipeline "$P45_PIPELINE_ABS" \
    --whitelist "$P45_BAD_WHITELIST" \
    --strict-source-set true \
    --require-active true 2>/dev/null)
  P45_WHITELIST_RC=$?
  set -e
  printf '%s\n' "$P45_OUT_WHITELIST" > "$REGRESSION_TMP/phase45_whitelist_signature.log"
  if [ "$P45_WHITELIST_RC" -ne 0 ] && echo "$P45_OUT_WHITELIST" | grep -q 'signature content_sha256 mismatch'; then
    check "Phase45:pipeline_trust_detects_signature_mismatch" "PASS"
  else
    check "Phase45:pipeline_trust_detects_signature_mismatch" "FAIL"
  fi
else
  check "Phase45:kit_integrity_detects_signature_mismatch" "FAIL"
  check "Phase45:pipeline_trust_detects_signature_mismatch" "FAIL"
fi

# ─── Phase 46: dual approval gate ───
echo "[phase 46] dual_approval_gate_round40"
DUAL_APPROVAL="$SCRIPT_DIR/kit_dual_approval_guard.py"
if [ -f "$DUAL_APPROVAL" ] && [ -f "$P45_MANIFEST" ] && [ -f "$P45_WHITELIST" ]; then
  P46_REPO="$REGRESSION_TMP/phase46_repo"
  rm -rf "$P46_REPO"
  mkdir -p "$P46_REPO/prompt-dsl-system/tools"
  cp "$P45_MANIFEST" "$P46_REPO/prompt-dsl-system/tools/kit_integrity_manifest.json"
  cp "$P45_WHITELIST" "$P46_REPO/prompt-dsl-system/tools/pipeline_trust_whitelist.json"
  (
    cd "$P46_REPO"
    git init -q >/dev/null 2>&1 || true
    git config user.email "regression@example.com" >/dev/null 2>&1 || true
    git config user.name "regression" >/dev/null 2>&1 || true
    git add . >/dev/null 2>&1 || true
    git commit -qm "phase46-baseline" >/dev/null 2>&1 || true
  )
  printf '\n' >> "$P46_REPO/prompt-dsl-system/tools/kit_integrity_manifest.json"

  P46_APPROVAL="$P46_REPO/prompt-dsl-system/tools/baseline_dual_approval.json"
  P46_OUT_JSON_NO="$REGRESSION_TMP/phase46_dual_no_approval.json"
  set +e
  P46_OUT_NO=$("$PYTHON_BIN" "$DUAL_APPROVAL" \
    --repo-root "$P46_REPO" \
    --approval-file "$P46_APPROVAL" \
    --required-approvers 2 \
    --require-git true \
    --out-json "$P46_OUT_JSON_NO" 2>/dev/null)
  P46_NO_RC=$?
  set -e
  printf '%s\n' "$P46_OUT_NO" > "$REGRESSION_TMP/phase46_dual_no.log"
  if [ "$P46_NO_RC" -ne 0 ] && echo "$P46_OUT_NO" | grep -q 'approval file missing'; then
    check "Phase46:dual_approval_blocks_changed_baseline_without_approval" "PASS"
  else
    check "Phase46:dual_approval_blocks_changed_baseline_without_approval" "FAIL"
  fi

  P46_FP=$("$PYTHON_BIN" - "$P46_OUT_JSON_NO" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
print(data.get("actual", {}).get("change_fingerprint", ""))
PY
)
  cat > "$P46_APPROVAL" <<EOF
{
  "approved": true,
  "change_fingerprint": "$P46_FP",
  "approvers": ["approver_a", "approver_b"],
  "approved_at": "2026-02-12T00:00:00Z",
  "note": "phase46 regression approval"
}
EOF

  set +e
  P46_OUT_OK=$("$PYTHON_BIN" "$DUAL_APPROVAL" \
    --repo-root "$P46_REPO" \
    --approval-file "$P46_APPROVAL" \
    --required-approvers 2 \
    --require-git true 2>/dev/null)
  P46_OK_RC=$?
  set -e
  printf '%s\n' "$P46_OUT_OK" > "$REGRESSION_TMP/phase46_dual_ok.log"
  if [ "$P46_OK_RC" -eq 0 ] && echo "$P46_OUT_OK" | grep -q '\[kit_dual_approval\] PASS'; then
    check "Phase46:dual_approval_accepts_matching_two_approvers" "PASS"
  else
    check "Phase46:dual_approval_accepts_matching_two_approvers" "FAIL"
  fi
else
  check "Phase46:dual_approval_blocks_changed_baseline_without_approval" "FAIL"
  check "Phase46:dual_approval_accepts_matching_two_approvers" "FAIL"
fi

# ─── Phase 47: CI mandatory gates workflow ───
echo "[phase 47] ci_mandatory_gates_workflow_round41"
CI_WORKFLOW="$REPO_ROOT/.github/workflows/kit_guardrails.yml"
if [ -f "$CI_WORKFLOW" ]; then
  check "Phase47:ci_workflow_exists" "PASS"
else
  check "Phase47:ci_workflow_exists" "FAIL"
fi
if [ -f "$CI_WORKFLOW" ] && grep -q 'run.sh validate -r .' "$CI_WORKFLOW" && \
   grep -q 'golden_path_regression.sh --repo-root .' "$CI_WORKFLOW" && \
   grep -Fq 'shard_group: [early, mid, late]' "$CI_WORKFLOW" && \
   grep -Fq -- '--shard-group "${{ matrix.shard_group }}"' "$CI_WORKFLOW"; then
  check "Phase47:ci_workflow_enforces_validate_and_golden" "PASS"
else
  check "Phase47:ci_workflow_enforces_validate_and_golden" "FAIL"
fi

# ─── Phase 48: HMAC strict smoke gate ───
echo "[phase 48] hmac_strict_smoke_round42"
HMAC_SMOKE="$SCRIPT_DIR/hmac_strict_smoke.py"
if [ -f "$HMAC_SMOKE" ]; then
  P48_OUT_JSON="$REGRESSION_TMP/phase48_hmac_smoke.json"
  set +e
  P48_OUT=$("$PYTHON_BIN" "$HMAC_SMOKE" --repo-root "$REPO_ROOT" --out-json "$P48_OUT_JSON" 2>/dev/null)
  P48_RC=$?
  set -e
  printf '%s\n' "$P48_OUT" > "$REGRESSION_TMP/phase48_hmac_smoke.log"
  if [ "$P48_RC" -eq 0 ] && echo "$P48_OUT" | grep -q '\[hmac_smoke\] PASS'; then
    check "Phase48:hmac_strict_smoke_pass" "PASS"
  else
    check "Phase48:hmac_strict_smoke_pass" "FAIL"
  fi
  P48_JSON_OK=$("$PYTHON_BIN" - "$P48_OUT_JSON" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print("0")
    raise SystemExit(0)

total = int(data.get("checks_total", 0))
passed = int(data.get("checks_passed", -1))
if data.get("passed") is True and total >= 6 and passed == total:
    print("1")
else:
    print("0")
PY
)
  if [ "$P48_JSON_OK" = "1" ]; then
    check "Phase48:hmac_strict_smoke_report_contract" "PASS"
  else
    check "Phase48:hmac_strict_smoke_report_contract" "FAIL"
  fi
else
  check "Phase48:hmac_strict_smoke_pass" "FAIL"
  check "Phase48:hmac_strict_smoke_report_contract" "FAIL"
fi

# ─── Phase 49: CI baseline approval + extra gates workflow checks ───
echo "[phase 49] ci_dual_approval_and_extra_gates_round43"
if [ -f "$CI_WORKFLOW" ] && grep -q 'kit_dual_approval_guard.py' "$CI_WORKFLOW" && grep -q 'git diff --name-only' "$CI_WORKFLOW"; then
  check "Phase49:ci_workflow_enforces_baseline_dual_approval_proof" "PASS"
else
  check "Phase49:ci_workflow_enforces_baseline_dual_approval_proof" "FAIL"
fi
if [ -f "$CI_WORKFLOW" ] && grep -q 'hmac_strict_smoke.py' "$CI_WORKFLOW" && grep -q 'fuzz_contract_pipeline_gate.py' "$CI_WORKFLOW"; then
  check "Phase49:ci_workflow_enforces_hmac_and_fuzz_gates" "PASS"
else
  check "Phase49:ci_workflow_enforces_hmac_and_fuzz_gates" "FAIL"
fi
if [ -f "$CI_WORKFLOW" ] && grep -q 'governance_consistency_guard.py' "$CI_WORKFLOW" && grep -q 'tool_syntax_guard.py' "$CI_WORKFLOW" && grep -q 'pipeline_trust_coverage_guard.py' "$CI_WORKFLOW"; then
  check "Phase49:ci_workflow_enforces_governance_syntax_trust_coverage_gates" "PASS"
else
  check "Phase49:ci_workflow_enforces_governance_syntax_trust_coverage_gates" "FAIL"
fi
if [ -f "$CI_WORKFLOW" ] && grep -q 'baseline_provenance_guard.py' "$CI_WORKFLOW" && grep -q 'gate_mutation_guard.py' "$CI_WORKFLOW" && grep -q 'performance_budget_guard.py' "$CI_WORKFLOW"; then
  check "Phase49:ci_workflow_enforces_provenance_mutation_performance_gates" "PASS"
else
  check "Phase49:ci_workflow_enforces_provenance_mutation_performance_gates" "FAIL"
fi
if [ -f "$CI_WORKFLOW" ] && \
   grep -Fq 'Upload Golden Shard Report (${{ matrix.shard_group }})' "$CI_WORKFLOW" && \
   grep -Fq 'name: golden-report-${{ matrix.shard_group }}' "$CI_WORKFLOW" && \
   grep -Fq 'golden-regression-summary:' "$CI_WORKFLOW" && \
   grep -Fq 'actions/download-artifact@v4' "$CI_WORKFLOW" && \
   grep -Fq 'pattern: golden-report-*' "$CI_WORKFLOW" && \
   grep -Fq 'merge-multiple: true' "$CI_WORKFLOW" && \
   grep -Fq 'Enforce Golden Shard Summary Contract' "$CI_WORKFLOW" && \
   grep -Fq 'golden_shard_summary_guard.py' "$CI_WORKFLOW" && \
   grep -Fq -- '--expected-shards early,mid,late' "$CI_WORKFLOW" && \
   grep -Fq -- '--require-overall-pass true' "$CI_WORKFLOW" && \
   grep -Fq -- '--require-full-check-pass true' "$CI_WORKFLOW" && \
   grep -Fq 'name: golden-report-summary' "$CI_WORKFLOW"; then
  check "Phase49:ci_workflow_enforces_shard_report_artifacts" "PASS"
else
  check "Phase49:ci_workflow_enforces_shard_report_artifacts" "FAIL"
fi

# ─── Phase 50: parser/contract fuzz robustness gate ───
echo "[phase 50] fuzz_gate_round44"
FUZZ_GATE="$SCRIPT_DIR/fuzz_contract_pipeline_gate.py"
if [ -f "$FUZZ_GATE" ]; then
  P50_OUT_JSON="$REGRESSION_TMP/phase50_fuzz_gate.json"
  set +e
  P50_OUT=$("$PYTHON_BIN" "$FUZZ_GATE" --repo-root "$REPO_ROOT" --iterations 300 --seed 20260212 --out-json "$P50_OUT_JSON" 2>/dev/null)
  P50_RC=$?
  set -e
  printf '%s\n' "$P50_OUT" > "$REGRESSION_TMP/phase50_fuzz_gate.log"
  if [ "$P50_RC" -eq 0 ] && echo "$P50_OUT" | grep -q '\[fuzz_gate\] PASS'; then
    check "Phase50:fuzz_gate_pass" "PASS"
  else
    check "Phase50:fuzz_gate_pass" "FAIL"
  fi
  P50_JSON_OK=$("$PYTHON_BIN" - "$P50_OUT_JSON" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print("0")
    raise SystemExit(0)

summary = data.get("summary", {}) if isinstance(data.get("summary"), dict) else {}
crash_total = int(summary.get("crash_total", -1))
violations = int(summary.get("structural_violations", -1))
if data.get("passed") is True and crash_total == 0 and violations == 0:
    print("1")
else:
    print("0")
PY
)
  if [ "$P50_JSON_OK" = "1" ]; then
    check "Phase50:fuzz_gate_report_contract" "PASS"
  else
    check "Phase50:fuzz_gate_report_contract" "FAIL"
  fi
else
  check "Phase50:fuzz_gate_pass" "FAIL"
  check "Phase50:fuzz_gate_report_contract" "FAIL"
fi

# ─── Phase 51: governance consistency guard ───
echo "[phase 51] governance_consistency_guard_round45"
GOVERNANCE_GUARD="$SCRIPT_DIR/governance_consistency_guard.py"
if [ -f "$GOVERNANCE_GUARD" ]; then
  P51_OUT_JSON="$REGRESSION_TMP/phase51_governance_consistency.json"
  set +e
  P51_OUT=$("$PYTHON_BIN" "$GOVERNANCE_GUARD" --repo-root "$REPO_ROOT" --out-json "$P51_OUT_JSON" 2>/dev/null)
  P51_RC=$?
  set -e
  printf '%s\n' "$P51_OUT" > "$REGRESSION_TMP/phase51_governance_consistency.log"
  if [ "$P51_RC" -eq 0 ] && echo "$P51_OUT" | grep -q '\[governance_consistency\] PASS'; then
    check "Phase51:governance_consistency_guard_pass" "PASS"
  else
    check "Phase51:governance_consistency_guard_pass" "FAIL"
  fi
  P51_JSON_OK=$("$PYTHON_BIN" - "$P51_OUT_JSON" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print("0")
    raise SystemExit(0)

summary = data.get("summary", {}) if isinstance(data.get("summary"), dict) else {}
if data.get("tool") == "governance_consistency_guard" and summary.get("passed") is True and int(summary.get("checks_total", 0)) >= 6:
    print("1")
else:
    print("0")
PY
)
  if [ "$P51_JSON_OK" = "1" ]; then
    check "Phase51:governance_consistency_report_contract" "PASS"
  else
    check "Phase51:governance_consistency_report_contract" "FAIL"
  fi
else
  check "Phase51:governance_consistency_guard_pass" "FAIL"
  check "Phase51:governance_consistency_report_contract" "FAIL"
fi

# ─── Phase 52: tool syntax guard ───
echo "[phase 52] tool_syntax_guard_round46"
TOOL_SYNTAX_GUARD="$SCRIPT_DIR/tool_syntax_guard.py"
if [ -f "$TOOL_SYNTAX_GUARD" ]; then
  P52_OUT_JSON="$REGRESSION_TMP/phase52_tool_syntax.json"
  set +e
  P52_OUT=$("$PYTHON_BIN" "$TOOL_SYNTAX_GUARD" --repo-root "$REPO_ROOT" --out-json "$P52_OUT_JSON" 2>/dev/null)
  P52_RC=$?
  set -e
  printf '%s\n' "$P52_OUT" > "$REGRESSION_TMP/phase52_tool_syntax.log"
  if [ "$P52_RC" -eq 0 ] && echo "$P52_OUT" | grep -q '\[tool_syntax_guard\] PASS'; then
    check "Phase52:tool_syntax_guard_pass" "PASS"
  else
    check "Phase52:tool_syntax_guard_pass" "FAIL"
  fi
  P52_JSON_OK=$("$PYTHON_BIN" - "$P52_OUT_JSON" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print("0")
    raise SystemExit(0)

summary = data.get("summary", {}) if isinstance(data.get("summary"), dict) else {}
actual = data.get("actual", {}) if isinstance(data.get("actual"), dict) else {}
if data.get("tool") == "tool_syntax_guard" and summary.get("passed") is True and int(actual.get("python_checked", 0)) > 0 and int(actual.get("shell_checked", 0)) > 0:
    print("1")
else:
    print("0")
PY
)
  if [ "$P52_JSON_OK" = "1" ]; then
    check "Phase52:tool_syntax_report_contract" "PASS"
  else
    check "Phase52:tool_syntax_report_contract" "FAIL"
  fi
else
  check "Phase52:tool_syntax_guard_pass" "FAIL"
  check "Phase52:tool_syntax_report_contract" "FAIL"
fi

# ─── Phase 53: pipeline trust coverage guard ───
echo "[phase 53] pipeline_trust_coverage_guard_round47"
TRUST_COVERAGE_GUARD="$SCRIPT_DIR/pipeline_trust_coverage_guard.py"
P53_WHITELIST="$REPO_ROOT/prompt-dsl-system/tools/pipeline_trust_whitelist.json"
P53_PIPELINE_REL="prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_kit_self_upgrade.md"
if [ -f "$TRUST_COVERAGE_GUARD" ] && [ -f "$PIPELINE_RUNNER" ] && [ -f "$P53_WHITELIST" ]; then
  P53_OUT_JSON="$REGRESSION_TMP/phase53_trust_coverage.json"
  set +e
  P53_OUT=$("$PYTHON_BIN" "$TRUST_COVERAGE_GUARD" \
    --repo-root "$REPO_ROOT" \
    --whitelist "$P53_WHITELIST" \
    --strict-source-set true \
    --require-active true \
    --out-json "$P53_OUT_JSON" 2>/dev/null)
  P53_RC=$?
  set -e
  printf '%s\n' "$P53_OUT" > "$REGRESSION_TMP/phase53_trust_coverage.log"
  if [ "$P53_RC" -eq 0 ] && echo "$P53_OUT" | grep -q '\[pipeline_trust_coverage\] PASS'; then
    check "Phase53:pipeline_trust_coverage_guard_pass" "PASS"
  else
    check "Phase53:pipeline_trust_coverage_guard_pass" "FAIL"
  fi
  P53_JSON_OK=$("$PYTHON_BIN" - "$P53_OUT_JSON" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print("0")
    raise SystemExit(0)

summary = data.get("summary", {}) if isinstance(data.get("summary"), dict) else {}
actual = data.get("actual", {}) if isinstance(data.get("actual"), dict) else {}
if data.get("tool") == "pipeline_trust_coverage_guard" and summary.get("passed") is True and int(actual.get("pipeline_count", 0)) >= 10:
    print("1")
else:
    print("0")
PY
)
  if [ "$P53_JSON_OK" = "1" ]; then
    check "Phase53:pipeline_trust_coverage_report_contract" "PASS"
  else
    check "Phase53:pipeline_trust_coverage_report_contract" "FAIL"
  fi

  P53_BAD_WHITELIST="$REGRESSION_TMP/phase53_bad_whitelist_coverage.json"
  cp "$P53_WHITELIST" "$P53_BAD_WHITELIST"
  "$PYTHON_BIN" - "$P53_BAD_WHITELIST" <<'PY'
import json
import hashlib
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
entries = data.get("entries")
if isinstance(entries, list):
    for item in entries:
        if isinstance(item, dict) and str(item.get("path", "")).endswith("pipeline_sql_oracle_to_dm8.md"):
            item["sha256"] = "e" * 64
            break

signature = data.get("signature")
if isinstance(signature, dict):
    payload = {k: data[k] for k in sorted(data.keys()) if k != "signature"}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature["scheme"] = "sha256"
    signature["content_sha256"] = hashlib.sha256(canonical).hexdigest()
    signature.pop("hmac_sha256", None)
    signature.pop("key_id", None)
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
  set +e
  P53_RUN_OUT=$(HONGZHI_PIPELINE_TRUST_WHITELIST="$P53_BAD_WHITELIST" \
    "$PYTHON_BIN" "$PIPELINE_RUNNER" run \
      --repo-root "$REPO_ROOT" \
      --module-path "$REPO_ROOT/prompt-dsl-system" \
      --pipeline "$P53_PIPELINE_REL" 2>/dev/null)
  P53_RUN_RC=$?
  set -e
  printf '%s\n' "$P53_RUN_OUT" > "$REGRESSION_TMP/phase53_runner_trust_coverage_block.log"
  if [ "$P53_RUN_RC" -ne 0 ] && echo "$P53_RUN_OUT" | grep -q '\[pipeline_trust_coverage\] FAIL'; then
    check "Phase53:pipeline_runner_blocks_non_selected_pipeline_hash_drift" "PASS"
  else
    check "Phase53:pipeline_runner_blocks_non_selected_pipeline_hash_drift" "FAIL"
  fi
else
  check "Phase53:pipeline_trust_coverage_guard_pass" "FAIL"
  check "Phase53:pipeline_trust_coverage_report_contract" "FAIL"
  check "Phase53:pipeline_runner_blocks_non_selected_pipeline_hash_drift" "FAIL"
fi

# ─── Phase 54: baseline provenance gate ───
echo "[phase 54] baseline_provenance_guard_round48"
P54_PROVENANCE_GUARD="$SCRIPT_DIR/baseline_provenance_guard.py"
P54_PROVENANCE_JSON="$REPO_ROOT/prompt-dsl-system/tools/baseline_provenance.json"
if [ -f "$P54_PROVENANCE_GUARD" ] && [ -f "$P54_PROVENANCE_JSON" ]; then
  P54_OUT_JSON="$REGRESSION_TMP/phase54_provenance_report.json"
  set +e
  P54_OUT_PASS=$("$PYTHON_BIN" "$P54_PROVENANCE_GUARD" verify \
    --repo-root "$REPO_ROOT" \
    --provenance "$P54_PROVENANCE_JSON" \
    --strict-source-set true \
    --out-json "$P54_OUT_JSON" 2>/dev/null)
  P54_PASS_RC=$?
  set -e
  printf '%s\n' "$P54_OUT_PASS" > "$REGRESSION_TMP/phase54_provenance_pass.log"
  if [ "$P54_PASS_RC" -eq 0 ] && echo "$P54_OUT_PASS" | grep -q '\[baseline_provenance\] PASS'; then
    check "Phase54:baseline_provenance_guard_pass" "PASS"
  else
    check "Phase54:baseline_provenance_guard_pass" "FAIL"
  fi

  P54_BAD_PROVENANCE="$REGRESSION_TMP/phase54_bad_provenance.json"
  cp "$P54_PROVENANCE_JSON" "$P54_BAD_PROVENANCE"
  "$PYTHON_BIN" - "$P54_BAD_PROVENANCE" <<'PY'
import hashlib
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
entries = data.get("entries")
if isinstance(entries, list):
    for item in entries:
        if isinstance(item, dict) and str(item.get("path", "")).endswith("pipeline_trust_whitelist.json"):
            item["sha256"] = "d" * 64
            break
sig = data.get("signature")
if isinstance(sig, dict):
    payload = {k: data[k] for k in sorted(data.keys()) if k != "signature"}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sig["scheme"] = "sha256"
    sig["content_sha256"] = hashlib.sha256(canonical).hexdigest()
    sig.pop("hmac_sha256", None)
    sig.pop("key_id", None)
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
  set +e
  P54_OUT_FAIL=$("$PYTHON_BIN" "$P54_PROVENANCE_GUARD" verify \
    --repo-root "$REPO_ROOT" \
    --provenance "$P54_BAD_PROVENANCE" \
    --strict-source-set true 2>/dev/null)
  P54_FAIL_RC=$?
  set -e
  printf '%s\n' "$P54_OUT_FAIL" > "$REGRESSION_TMP/phase54_provenance_fail.log"
  if [ "$P54_FAIL_RC" -ne 0 ] && echo "$P54_OUT_FAIL" | grep -q 'sha256 mismatch'; then
    check "Phase54:baseline_provenance_detects_hash_mismatch" "PASS"
  else
    check "Phase54:baseline_provenance_detects_hash_mismatch" "FAIL"
  fi
else
  check "Phase54:baseline_provenance_guard_pass" "FAIL"
  check "Phase54:baseline_provenance_detects_hash_mismatch" "FAIL"
fi

# ─── Phase 55: mutation resilience gate ───
echo "[phase 55] mutation_guard_round49"
P55_MUTATION_GUARD="$SCRIPT_DIR/gate_mutation_guard.py"
if [ -f "$P55_MUTATION_GUARD" ]; then
  P55_OUT_JSON="$REGRESSION_TMP/phase55_mutation_guard.json"
  set +e
  P55_OUT=$("$PYTHON_BIN" "$P55_MUTATION_GUARD" --repo-root "$REPO_ROOT" --out-json "$P55_OUT_JSON" 2>/dev/null)
  P55_RC=$?
  set -e
  printf '%s\n' "$P55_OUT" > "$REGRESSION_TMP/phase55_mutation_guard.log"
  if [ "$P55_RC" -eq 0 ] && echo "$P55_OUT" | grep -q '\[mutation_guard\] PASS'; then
    check "Phase55:mutation_guard_pass" "PASS"
  else
    check "Phase55:mutation_guard_pass" "FAIL"
  fi
  P55_JSON_OK=$("$PYTHON_BIN" - "$P55_OUT_JSON" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print("0")
    raise SystemExit(0)

summary = data.get("summary", {}) if isinstance(data.get("summary"), dict) else {}
if data.get("tool") == "gate_mutation_guard" and summary.get("passed") is True and int(summary.get("cases_total", 0)) >= 4:
    print("1")
else:
    print("0")
PY
)
  if [ "$P55_JSON_OK" = "1" ]; then
    check "Phase55:mutation_guard_report_contract" "PASS"
  else
    check "Phase55:mutation_guard_report_contract" "FAIL"
  fi

  P55_CONC_A_LOG="$REGRESSION_TMP/phase55_mutation_guard_concurrent_a.log"
  P55_CONC_B_LOG="$REGRESSION_TMP/phase55_mutation_guard_concurrent_b.log"
  P55_CONC_A_JSON="$REGRESSION_TMP/phase55_mutation_guard_concurrent_a.json"
  P55_CONC_B_JSON="$REGRESSION_TMP/phase55_mutation_guard_concurrent_b.json"
  set +e
  "$PYTHON_BIN" "$P55_MUTATION_GUARD" --repo-root "$REPO_ROOT" --out-json "$P55_CONC_A_JSON" > "$P55_CONC_A_LOG" 2>&1 &
  P55_PID_A=$!
  "$PYTHON_BIN" "$P55_MUTATION_GUARD" --repo-root "$REPO_ROOT" --out-json "$P55_CONC_B_JSON" > "$P55_CONC_B_LOG" 2>&1 &
  P55_PID_B=$!
  wait "$P55_PID_A"
  P55_CONC_RC_A=$?
  wait "$P55_PID_B"
  P55_CONC_RC_B=$?
  set -e
  if [ "$P55_CONC_RC_A" -eq 0 ] && [ "$P55_CONC_RC_B" -eq 0 ] \
     && grep -q '\[mutation_guard\] PASS' "$P55_CONC_A_LOG" \
     && grep -q '\[mutation_guard\] PASS' "$P55_CONC_B_LOG"; then
    check "Phase55:mutation_guard_concurrent_runs_pass" "PASS"
  else
    check "Phase55:mutation_guard_concurrent_runs_pass" "FAIL"
  fi
else
  check "Phase55:mutation_guard_pass" "FAIL"
  check "Phase55:mutation_guard_report_contract" "FAIL"
  check "Phase55:mutation_guard_concurrent_runs_pass" "FAIL"
fi

# ─── Phase 56: performance budget gate ───
echo "[phase 56] performance_guard_round50"
P56_PERF_GUARD="$SCRIPT_DIR/performance_budget_guard.py"
if [ -f "$P56_PERF_GUARD" ]; then
  P56_OUT_JSON="$REGRESSION_TMP/phase56_performance_guard.json"
  set +e
  P56_OUT=$("$PYTHON_BIN" "$P56_PERF_GUARD" --repo-root "$REPO_ROOT" --out-json "$P56_OUT_JSON" 2>/dev/null)
  P56_RC=$?
  set -e
  printf '%s\n' "$P56_OUT" > "$REGRESSION_TMP/phase56_performance_guard.log"
  if [ "$P56_RC" -eq 0 ] && echo "$P56_OUT" | grep -q '\[performance_guard\] PASS'; then
    check "Phase56:performance_guard_pass" "PASS"
  else
    check "Phase56:performance_guard_pass" "FAIL"
  fi
  P56_JSON_OK=$("$PYTHON_BIN" - "$P56_OUT_JSON" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print("0")
    raise SystemExit(0)

summary = data.get("summary", {}) if isinstance(data.get("summary"), dict) else {}
actual = data.get("actual", {}) if isinstance(data.get("actual"), dict) else {}
checks = actual.get("checks") if isinstance(actual.get("checks"), list) else []
if data.get("tool") == "performance_budget_guard" and summary.get("passed") is True and len(checks) >= 4:
    print("1")
else:
    print("0")
PY
)
  if [ "$P56_JSON_OK" = "1" ]; then
    check "Phase56:performance_guard_report_contract" "PASS"
  else
    check "Phase56:performance_guard_report_contract" "FAIL"
  fi

  P56_TREND_HISTORY="$REGRESSION_TMP/phase56_perf_history.jsonl"
  "$PYTHON_BIN" - "$P56_TREND_HISTORY" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
rows = []
for _ in range(6):
    rows.append({
        "tool": "performance_budget_guard",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "summary": {"passed": True, "checks_total": 4, "checks_failed": 0},
        "actual": {
            "total_seconds": 0.05,
            "checks": [
                {"name": "kit_selfcheck", "seconds": 0.01, "returncode": 0},
                {"name": "governance_consistency_guard", "seconds": 0.01, "returncode": 0},
                {"name": "tool_syntax_guard", "seconds": 0.01, "returncode": 0},
                {"name": "pipeline_trust_coverage_guard", "seconds": 0.01, "returncode": 0},
            ],
        },
    })
path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
PY
  set +e
  P56_TREND_OUT=$("$PYTHON_BIN" "$P56_PERF_GUARD" \
    --repo-root "$REPO_ROOT" \
    --history-file "$P56_TREND_HISTORY" \
    --history-window 6 \
    --trend-min-samples 5 \
    --trend-max-ratio 1.2 \
    --trend-enforce true \
    --history-write false 2>/dev/null)
  P56_TREND_RC=$?
  set -e
  printf '%s\n' "$P56_TREND_OUT" > "$REGRESSION_TMP/phase56_performance_trend_block.log"
  if [ "$P56_TREND_RC" -ne 0 ] && echo "$P56_TREND_OUT" | grep -q 'trend total regression'; then
    check "Phase56:performance_trend_regression_block" "PASS"
  else
    check "Phase56:performance_trend_regression_block" "FAIL"
  fi
else
  check "Phase56:performance_guard_pass" "FAIL"
  check "Phase56:performance_guard_report_contract" "FAIL"
  check "Phase56:performance_trend_regression_block" "FAIL"
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

fi

# ─── Cleanup: restore original state ───
echo "[cleanup] restoring original state"
cleanup_state

# ─── Report ───
cat > "$REPORT_FILE" <<EOF
# Golden Path Regression Report

Generated: $REPORT_TIMESTAMP
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

if [ -n "$REPORT_OUT_PATH" ]; then
  mkdir -p "$(dirname "$REPORT_OUT_PATH")"
  cp "$REPORT_FILE" "$REPORT_OUT_PATH"
  echo "report_out: $REPORT_OUT_PATH"
fi

if [ "$CLEAN_TMP" = "true" ]; then
  rm -rf "$REGRESSION_TMP"
  echo "cleanup_tmp: $REGRESSION_TMP"
fi

exit $RC
