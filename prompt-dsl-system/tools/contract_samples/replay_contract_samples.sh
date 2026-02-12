#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${1:-.}"
if [ "${1:-}" = "--repo-root" ] && [ -n "${2:-}" ]; then
  REPO_ROOT="$2"
fi
REPO_ROOT="$(cd "$REPO_ROOT" && pwd -P)"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
TOOLS_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"
VALIDATOR="$TOOLS_DIR/contract_validator.py"
SCHEMA_V1="$TOOLS_DIR/contract_schema_v1.json"
SCHEMA_V2="$TOOLS_DIR/contract_schema_v2.json"

if [ ! -f "$VALIDATOR" ]; then
  echo "[contract_replay] missing validator: $VALIDATOR" >&2
  exit 2
fi

SCHEMA="$SCHEMA_V1"
if [ -f "$SCHEMA_V2" ]; then
  SCHEMA="$SCHEMA_V2"
fi

BASELINE_ARGS=()
if [ "$SCHEMA" = "$SCHEMA_V2" ] && [ -f "$SCHEMA_V1" ]; then
  BASELINE_ARGS=(--baseline-schema "$SCHEMA_V1")
fi

SAMPLES=(
  "$SCRIPT_DIR/sample_kit_caps_v2.log"
  "$SCRIPT_DIR/sample_hongzhi_caps_v2.log"
  "$SCRIPT_DIR/sample_hongzhi_gov_block_v2.log"
)

for sample in "${SAMPLES[@]}"; do
  if [ ! -f "$sample" ]; then
    echo "[contract_replay] missing sample: $sample" >&2
    exit 2
  fi
  echo "[contract_replay] validating $(basename "$sample") with $(basename "$SCHEMA")"
  "$PYTHON_BIN" "$VALIDATOR" --schema "$SCHEMA" "${BASELINE_ARGS[@]}" --file "$sample"
done

echo "[contract_replay] PASS"
