#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-.}"
MODULE_PATH="${MODULE_PATH:-}"
PIPELINE_PATH="${PIPELINE_PATH:-}"
MOVES_JSON="${MOVES_JSON:-}"
SCAN_REPORT_JSON="${SCAN_REPORT_JSON:-}"

require_var() {
  local name="$1"
  local value="$2"
  if [ -z "$value" ]; then
    echo "[ERROR] $name is required. Export $name first." >&2
    exit 2
  fi
}

require_var "MODULE_PATH" "$MODULE_PATH"
require_var "PIPELINE_PATH" "$PIPELINE_PATH"
require_var "MOVES_JSON" "$MOVES_JSON"
require_var "SCAN_REPORT_JSON" "$SCAN_REPORT_JSON"

echo "[health-runbook] mode=${RUNBOOK_MODE:-safe} repo_root=${REPO_ROOT}"

echo "[STEP 1] Verify Residual References"
echo "Purpose: 先把 verify FAIL 收敛到 PASS，终止 bypass 风险升级。"
./prompt-dsl-system/tools/run.sh verify-followup-fixes -r "${REPO_ROOT}" --moves "${MOVES_JSON}"

echo "[STEP 2] Run Plan (No ACK Auto)"
echo "Purpose: 仅做计划生成，验证当前是否还能无风险推进。"
./prompt-dsl-system/tools/run.sh run -r "${REPO_ROOT}" -m "${MODULE_PATH}" --pipeline "${PIPELINE_PATH}"

echo "[STEP 3] ACK Note Guidance"
echo "Purpose: 如确需临时放行，先记录人工理由保证审计可追溯。"
echo "Manual step: no direct command in this stage."

echo "[STEP 4] Verify Until PASS"
echo "Purpose: 持续验证残留引用，直到 verify 报告为 PASS。"
./prompt-dsl-system/tools/run.sh verify-followup-fixes -r "${REPO_ROOT}" --moves "${MOVES_JSON}"

echo "[STEP 5] Generate Follow-up Patch Plan"
echo "Purpose: 只生成补丁计划，不直接改文件。"
./prompt-dsl-system/tools/run.sh apply-followup-fixes -r "${REPO_ROOT}" --scan-report "${SCAN_REPORT_JSON}" --mode plan

echo "[STEP 6] Re-Verify"
echo "Purpose: 再次验证补丁计划后的残留状态。"
./prompt-dsl-system/tools/run.sh verify-followup-fixes -r "${REPO_ROOT}" --moves "${MOVES_JSON}"
