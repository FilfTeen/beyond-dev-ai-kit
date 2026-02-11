#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="/Users/dwight/Downloads/【洪智科技】本地存档/beyond-dev-ai-kit"
SNAPSHOT_ID="snapshot_20260210T051307Z_d2726d47"
CHANGED_FILES_FILE="/Users/dwight/Downloads/【洪智科技】本地存档/beyond-dev-ai-kit/prompt-dsl-system/tools/snapshots/snapshot_20260210T051307Z_d2726d47/changed_files.txt"
DRY_RUN="${DRY_RUN:-1}"
SKIPPED=0

echo "[restore] snapshot=${SNAPSHOT_ID} repo=${REPO_ROOT}"
echo "[restore] target list: ${CHANGED_FILES_FILE}"
echo "[restore][WARN] file-level restore may discard uncommitted changes for listed files."
if [ "${DRY_RUN}" != "0" ]; then
  echo "[restore] DRY_RUN=${DRY_RUN} (preview only). Set DRY_RUN=0 to execute."
fi
cd "${REPO_ROOT}"

if [ ! -f "${CHANGED_FILES_FILE}" ]; then
  echo "[restore][ERROR] changed files list not found: ${CHANGED_FILES_FILE}" >&2
  exit 2
fi

run_cmd() {
  if [ "${DRY_RUN}" = "0" ]; then
    "$@"
  else
    echo "[dry-run] $*"
  fi
}

echo "[restore][ERROR] no vcs detected; file-level auto-restore unavailable." >&2
if [ "${DRY_RUN}" = "0" ]; then
  exit 2
fi
