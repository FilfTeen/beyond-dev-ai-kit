#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-.}"
DRY_RUN="${DRY_RUN:-1}"
MODULE_PATH="${MODULE_PATH:-}"
PIPELINE_PATH="${PIPELINE_PATH:-}"
MOVES_JSON="${MOVES_JSON:-}"
SCAN_REPORT_JSON="${SCAN_REPORT_JSON:-}"

run_cmd() {
  local cmd="$1"
  if [ "${DRY_RUN}" = "1" ]; then
    echo "[DRY_RUN] ${cmd}"
  else
    echo "[RUN] ${cmd}"
    eval "${cmd}"
  fi
}

require_var() {
  local name="$1"
  local val="${!name:-}"
  if [ -z "${val}" ]; then
    echo "[ERROR] Missing required variable: ${name}" >&2
    exit 2
  fi
}

echo '[S0] Generate diff evidence'
run_cmd "./prompt-dsl-system/tools/run.sh trace-diff -r . --a trace-bisect-good-001 --b trace-dc6cd01395f14cd2b762229630586cda --scan-deliveries false"

echo '[S1] Inspect bypass evidence for bad trace'
run_cmd "./prompt-dsl-system/tools/run.sh trace-open -r . --trace-id trace-dc6cd01395f14cd2b762229630586cda"

echo '[S2] Force verification before any further promotion'
require_var MOVES_JSON
run_cmd "./prompt-dsl-system/tools/run.sh verify-followup-fixes -r . --moves ${MOVES_JSON}"

echo '[S3] Re-check release gate with loop protection'
require_var MODULE_PATH
require_var PIPELINE_PATH
run_cmd "./prompt-dsl-system/tools/run.sh run -r . -m ${MODULE_PATH} --pipeline ${PIPELINE_PATH} --verify-gate true --fail-on-loop true"

echo '[S4] Generate follow-up patch plan (plan only)'
require_var SCAN_REPORT_JSON
run_cmd "./prompt-dsl-system/tools/run.sh apply-followup-fixes -r . --scan-report ${SCAN_REPORT_JSON} --mode plan"

