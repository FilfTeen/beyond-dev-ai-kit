#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="/Users/dwight/Downloads/【洪智科技】本地存档/beyond-dev-ai-kit"
SNAPSHOT_ID="snapshot_20260210T051307Z_d2726d47"
DRY_RUN="${DRY_RUN:-1}"

echo "[restore] snapshot=${SNAPSHOT_ID} repo=${REPO_ROOT}"
echo "[restore][WARN] destructive restore may discard uncommitted changes."
if [ "${DRY_RUN}" != "0" ]; then
  echo "[restore] DRY_RUN=${DRY_RUN} (preview only). Set DRY_RUN=0 to execute."
fi
cd "${REPO_ROOT}"

run_cmd() {
  if [ "${DRY_RUN}" = "0" ]; then
    "$@"
  else
    echo "[dry-run] $*"
  fi
}

echo "[restore][ERROR] no vcs detected; full auto-restore unavailable." >&2
if [ "${DRY_RUN}" = "0" ]; then
  exit 2
fi
