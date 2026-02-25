#!/usr/bin/env bash
# Atomic baseline rebuild in strict dependency order.
# Order: trust_whitelist → fact_baseline_refresh → provenance → manifest
#
# Usage:
#   bash prompt-dsl-system/tools/baseline_rebuild_all.sh --repo-root .

set -euo pipefail

REPO_ROOT="."
while [ $# -gt 0 ]; do
  case "$1" in
    --repo-root) shift; REPO_ROOT="$1" ;;
    -h|--help)
      echo "Usage: bash $0 --repo-root <path>"
      echo "Rebuilds all baselines in strict dependency order: trust → provenance → manifest"
      exit 0
      ;;
    *) echo "error: unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

REPO_ROOT="$(cd "$REPO_ROOT" && pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"

TRUST="$REPO_ROOT/prompt-dsl-system/tools/pipeline_trust_whitelist.json"
PROVENANCE="$REPO_ROOT/prompt-dsl-system/tools/baseline_provenance.json"
MANIFEST="$REPO_ROOT/prompt-dsl-system/tools/kit_integrity_manifest.json"

echo "[baseline_rebuild] step 1/4: pipeline_trust_whitelist"
"$PYTHON_BIN" "$SCRIPT_DIR/pipeline_trust_guard.py" build \
  --repo-root "$REPO_ROOT" --whitelist "$TRUST"

echo "[baseline_rebuild] step 2/4: FACT_BASELINE key counters"
"$PYTHON_BIN" "$SCRIPT_DIR/fact_baseline_refresh.py" \
  --repo-root "$REPO_ROOT" \
  --fact-file prompt-dsl-system/00_conventions/FACT_BASELINE.md

echo "[baseline_rebuild] step 3/4: baseline_provenance"
"$PYTHON_BIN" "$SCRIPT_DIR/baseline_provenance_guard.py" build \
  --repo-root "$REPO_ROOT" --provenance "$PROVENANCE"

echo "[baseline_rebuild] step 4/4: kit_integrity_manifest"
"$PYTHON_BIN" "$SCRIPT_DIR/kit_integrity_guard.py" build \
  --repo-root "$REPO_ROOT" --manifest "$MANIFEST"

echo ""
echo "[baseline_rebuild] verifying..."
"$PYTHON_BIN" "$SCRIPT_DIR/kit_integrity_guard.py" verify \
  --repo-root "$REPO_ROOT" --manifest "$MANIFEST" --strict-source-set true
"$PYTHON_BIN" "$SCRIPT_DIR/baseline_provenance_guard.py" verify \
  --repo-root "$REPO_ROOT" --provenance "$PROVENANCE" --strict-source-set true

echo "[baseline_rebuild] ALL PASS — baselines consistent"
