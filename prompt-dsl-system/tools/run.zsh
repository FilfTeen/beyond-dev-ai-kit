#!/usr/bin/env zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
# Keep behavior aligned with run.sh, including -r/-m short options.
exec "${SCRIPT_DIR}/run.sh" "$@"
