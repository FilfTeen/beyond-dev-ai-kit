#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="/usr/bin/python3"
MARKER_REL="prompt-dsl-system/05_skill_registry/skills.json"
TOKEN_JSON_REL_DEFAULT="prompt-dsl-system/tools/RISK_GATE_TOKEN.json"
RISK_GATE_REPORT_REL_DEFAULT="prompt-dsl-system/tools/risk_gate_report.json"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
RUNNER_PATH="${SCRIPT_DIR}/pipeline_runner.py"
ROLLBACK_HELPER_PATH="${SCRIPT_DIR}/rollback_helper.py"
TOKEN_RECENCY_PATH="${SCRIPT_DIR}/token_recency.py"
runner_global_args=()

find_repo_root() {
  local start="$1"
  local cur
  cur="$(cd "$start" && pwd -P)"

  while true; do
    if [ -f "${cur}/${MARKER_REL}" ]; then
      printf '%s\n' "$cur"
      return 0
    fi

    if [ "$cur" = "/" ]; then
      return 1
    fi

    cur="$(dirname "$cur")"
  done
}

parse_bool() {
  local raw="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  case "$raw" in
    1|true|yes|on)
      printf '1\n'
      return 0
      ;;
    0|false|no|off)
      printf '0\n'
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

normalize_path_allow_missing() {
  local path="$1"
  if [ "${path#/}" = "$path" ]; then
    path="$PWD/$path"
  fi

  local dir
  dir="$(dirname "$path")"
  local base
  base="$(basename "$path")"
  if [ -d "$dir" ]; then
    dir="$(cd "$dir" && pwd -P)"
    printf '%s/%s\n' "$dir" "$base"
  else
    printf '%s\n' "$path"
  fi
}

to_repo_relative() {
  local repo_root="$1"
  local path="$2"
  "$PYTHON_BIN" - "$repo_root" "$path" <<'PY'
import pathlib, sys
repo = pathlib.Path(sys.argv[1]).resolve()
path = pathlib.Path(sys.argv[2]).resolve()
try:
    print(path.relative_to(repo).as_posix())
except Exception:
    print(str(path))
PY
}

read_ack_token_from_json() {
  local token_file="$1"
  "$PYTHON_BIN" - "$token_file" <<'PY'
import json, sys
path = sys.argv[1]
try:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
except Exception:
    raise SystemExit(2)

token = ''
if isinstance(data, dict):
    token_value = data.get('token')
    if isinstance(token_value, str):
        token = token_value.strip()
    elif isinstance(token_value, dict):
        nested = token_value.get('value')
        if isinstance(nested, str):
            token = nested.strip()
if token:
    print(token)
    raise SystemExit(0)
raise SystemExit(1)
PY
}

resolve_risk_gate_report_path() {
  local repo_root="$1"
  shift
  local -a cmd_args=("$@")
  local loop_output_dir_rel="prompt-dsl-system/tools"
  local arg
  local value
  local next

  for (( i=0; i<${#cmd_args[@]}; i++ )); do
    arg="${cmd_args[$i]}"
    case "$arg" in
      --loop-output-dir)
        next=$((i + 1))
        if [ "$next" -lt "${#cmd_args[@]}" ]; then
          loop_output_dir_rel="${cmd_args[$next]}"
          i=$next
        fi
        ;;
      --loop-output-dir=*)
        loop_output_dir_rel="${arg#*=}"
        ;;
    esac
  done

  value="$loop_output_dir_rel"
  if [ "${value#/}" = "$value" ]; then
    value="$repo_root/$value"
  fi
  value="$(normalize_path_allow_missing "$value")"
  printf '%s\n' "$(normalize_path_allow_missing "$value/risk_gate_report.json")"
}

resolve_output_token_json_path() {
  local repo_root="$1"
  shift
  local -a cmd_args=("$@")
  local output_dir_rel="prompt-dsl-system/tools"
  local arg
  local value
  local next

  for (( i=0; i<${#cmd_args[@]}; i++ )); do
    arg="${cmd_args[$i]}"
    case "$arg" in
      --output-dir)
        next=$((i + 1))
        if [ "$next" -lt "${#cmd_args[@]}" ]; then
          output_dir_rel="${cmd_args[$next]}"
          i=$next
        fi
        ;;
      --output-dir=*)
        output_dir_rel="${arg#*=}"
        ;;
    esac
  done

  value="$output_dir_rel"
  if [ "${value#/}" = "$value" ]; then
    value="$repo_root/$value"
  fi
  value="$(normalize_path_allow_missing "$value")"
  printf '%s\n' "$(normalize_path_allow_missing "$value/RISK_GATE_TOKEN.json")"
}

read_auto_ack_policy_from_report() {
  local report_file="$1"
  "$PYTHON_BIN" - "$report_file" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(2)

def b(v):
    return "1" if v is True else "0"

allow = b(data.get("auto_ack_allowed"))
deny = data.get("auto_ack_denied_reason")
deny = deny if isinstance(deny, str) else ""
move_available = b(data.get("move_plan_available"))
move_high_risk = data.get("move_plan_high_risk")
if isinstance(move_high_risk, (int, float)):
    move_high_risk = str(int(move_high_risk))
else:
    move_high_risk = ""

blockers_raw = data.get("move_plan_blockers")
if isinstance(blockers_raw, list):
    blockers = [str(x).strip().replace("\n", " ") for x in blockers_raw if str(x).strip()]
else:
    blockers = []

print(f"ALLOW={allow}")
print(f"DENY={deny}")
print(f"MOVE_AVAILABLE={move_available}")
print(f"MOVE_HIGH_RISK={move_high_risk}")
print(f"BLOCKERS={' || '.join(blockers)}")
PY
}

build_hint_command() {
  local sub="$1"
  shift
  local -a src=("$@")
  local -a out=("./prompt-dsl-system/tools/run.sh" "$sub")
  local skip_next=0
  local arg
  local lower

  for (( i=0; i<${#src[@]}; i++ )); do
    arg="${src[$i]}"

    if [ "$skip_next" -eq 1 ]; then
      skip_next=0
      continue
    fi

    case "$arg" in
      --ack)
        skip_next=1
        continue
        ;;
      --ack=*)
        continue
        ;;
    esac

    lower="$(printf '%s' "$arg" | tr '[:upper:]' '[:lower:]')"
    case "$lower" in
      --*token*|--*password*|--*passwd*|--*secret*|--*credential*|--*auth*|--*api*key*)
        if [[ "$arg" == *=* ]]; then
          out+=("${arg%%=*}=***")
        else
          out+=("$arg" "***")
          skip_next=1
        fi
        ;;
      *)
        out+=("$arg")
        ;;
    esac
  done

  out+=("--ack-latest")

  local cmd=""
  for arg in "${out[@]}"; do
    if [[ "$arg" == *[[:space:]]* ]]; then
      escaped="${arg//\"/\\\"}"
      cmd+="\"$escaped\" "
    else
      cmd+="$arg "
    fi
  done
  printf '%s\n' "${cmd% }"
}

run_runner_once() {
  local sub="$1"
  shift
  local -a invoke_args=("$@")
  local -a cmd=("$PYTHON_BIN" "$RUNNER_PATH")
  if [ "${#runner_global_args[@]}" -gt 0 ]; then
    cmd+=("${runner_global_args[@]}")
  fi
  cmd+=("$sub")
  cmd+=("${invoke_args[@]}")
  "${cmd[@]}"
  return $?
}

run_rollback_once() {
  local -a invoke_args=("$@")
  local -a cmd=("$PYTHON_BIN" "$ROLLBACK_HELPER_PATH")
  cmd+=("${invoke_args[@]}")
  "${cmd[@]}"
  return $?
}

if [ ! -x "$PYTHON_BIN" ]; then
  echo "[ERROR] Required interpreter not found: $PYTHON_BIN" >&2
  exit 2
fi

if [ ! -f "$RUNNER_PATH" ]; then
  echo "[ERROR] pipeline_runner.py not found: $RUNNER_PATH" >&2
  exit 2
fi

repo_root=""
default_root="$(cd "${SCRIPT_DIR}/../.." && pwd -P)"
if [ -f "${default_root}/${MARKER_REL}" ]; then
  repo_root="$default_root"
else
  repo_root="$(find_repo_root "$SCRIPT_DIR" || true)"
  if [ -z "$repo_root" ]; then
    repo_root="$(find_repo_root "$PWD" || true)"
  fi
fi

if [ -z "$repo_root" ]; then
  echo "[ERROR] Could not locate repo root. Expected marker: ${MARKER_REL}" >&2
  echo "[ERROR] Suggestion: cd to beyond-dev-ai-kit and rerun." >&2
  exit 2
fi

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <list|validate|run|intent|debug-guard|apply-move|resolve-move-conflicts|scan-followup|apply-followup-fixes|verify-followup-fixes|snapshot-restore-guide|snapshot-prune|snapshot-index|snapshot-open|trace-index|trace-open|trace-diff|trace-bisect|rollback|selfcheck|self-upgrade> [args...]" >&2
  exit 2
fi

subcommand="$1"
requested_subcommand="$subcommand"
shift

case "$subcommand" in
  list|validate|run|intent|debug-guard|apply-move|resolve-move-conflicts|scan-followup|apply-followup-fixes|verify-followup-fixes|snapshot-restore-guide|snapshot-prune|snapshot-index|snapshot-open|trace-index|trace-open|trace-diff|trace-bisect|rollback|selfcheck|self-upgrade) ;;
  *)
    echo "[ERROR] Unsupported subcommand: $subcommand" >&2
    echo "Usage: $0 <list|validate|run|intent|debug-guard|apply-move|resolve-move-conflicts|scan-followup|apply-followup-fixes|verify-followup-fixes|snapshot-restore-guide|snapshot-prune|snapshot-index|snapshot-open|trace-index|trace-open|trace-diff|trace-bisect|rollback|selfcheck|self-upgrade> [args...]" >&2
    exit 2
    ;;
esac

# Wrapper-only options.
auto_ack_latest=0
ack_hint_window="10"
no_ack_hint=0
ack_latest=0
ack_file_raw=""
strict_self_upgrade=0
no_snapshot_requested=0
policy_path_raw=""
policy_overrides=()

# Short option normalization: -r -> --repo-root, -m -> --module-path.
converted_args=()
while [ "$#" -gt 0 ]; do
  arg="$1"
  shift
  case "$arg" in
    --auto-ack-latest)
      auto_ack_latest=1
      ;;
    --auto-ack-latest=*)
      parsed_bool="$(parse_bool "${arg#*=}" || true)"
      if [ -z "$parsed_bool" ]; then
        echo "[ERROR] Invalid value for --auto-ack-latest: ${arg#*=}" >&2
        exit 2
      fi
      auto_ack_latest="$parsed_bool"
      ;;
    --ack-hint-window)
      if [ "$#" -lt 1 ]; then
        echo "[ERROR] Missing value for --ack-hint-window" >&2
        exit 2
      fi
      ack_hint_window="$1"
      shift
      ;;
    --ack-hint-window=*)
      ack_hint_window="${arg#*=}"
      ;;
    --no-ack-hint)
      no_ack_hint=1
      ;;
    --ack-file)
      if [ "$#" -lt 1 ]; then
        echo "[ERROR] Missing value for --ack-file" >&2
        exit 2
      fi
      ack_file_raw="$1"
      shift
      ;;
    --ack-file=*)
      ack_file_raw="${arg#*=}"
      ;;
    --strict-self-upgrade)
      strict_self_upgrade=1
      ;;
    --strict-self-upgrade=*)
      parsed_bool="$(parse_bool "${arg#*=}" || true)"
      if [ -z "$parsed_bool" ]; then
        echo "[ERROR] Invalid value for --strict-self-upgrade: ${arg#*=}" >&2
        exit 2
      fi
      strict_self_upgrade="$parsed_bool"
      ;;
    --ack-latest)
      ack_latest=1
      ;;
    --policy)
      if [ "$#" -lt 1 ]; then
        echo "[ERROR] Missing value for --policy" >&2
        exit 2
      fi
      policy_path_raw="$1"
      shift
      ;;
    --policy=*)
      policy_path_raw="${arg#*=}"
      ;;
    --policy-override)
      if [ "$#" -lt 1 ]; then
        echo "[ERROR] Missing value for --policy-override" >&2
        exit 2
      fi
      policy_overrides+=("$1")
      shift
      ;;
    --policy-override=*)
      policy_overrides+=("${arg#*=}")
      ;;
    --no-snapshot)
      no_snapshot_requested=1
      converted_args+=("$arg")
      ;;
    -r)
      if [ "$#" -lt 1 ]; then
        echo "[ERROR] Missing value for -r/--repo-root" >&2
        exit 2
      fi
      converted_args+=("--repo-root" "$1")
      shift
      ;;
    -m)
      if [ "$#" -lt 1 ]; then
        echo "[ERROR] Missing value for -m/--module-path" >&2
        exit 2
      fi
      converted_args+=("--module-path" "$1")
      shift
      ;;
    -r=*)
      converted_args+=("--repo-root=${arg#*=}")
      ;;
    -m=*)
      converted_args+=("--module-path=${arg#*=}")
      ;;
    *)
      converted_args+=("$arg")
      ;;
  esac
done
if [ "${#converted_args[@]}" -gt 0 ]; then
  args=("${converted_args[@]}")
else
  args=()
fi

if [ "$subcommand" = "self-upgrade" ]; then
  has_pipeline_arg=0
  has_module_path_arg=0
  for arg in "${args[@]-}"; do
    case "$arg" in
      --pipeline|--pipeline=*)
        has_pipeline_arg=1
        ;;
      --module-path|--module-path=*)
        has_module_path_arg=1
        ;;
    esac
  done

  if [ "$has_module_path_arg" -eq 0 ]; then
    if [ "${#args[@]}" -gt 0 ]; then
      args=("--module-path" "." "${args[@]}")
    else
      args=("--module-path" ".")
    fi
  fi

  if [ "$has_pipeline_arg" -eq 0 ]; then
    args+=("--pipeline" "prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_kit_self_upgrade.md")
  fi

  subcommand="run"
fi

if [ "$requested_subcommand" = "self-upgrade" ] && [ -n "${HONGZHI_SELF_UPGRADE_STRICT:-}" ]; then
  parsed_env_strict="$(parse_bool "${HONGZHI_SELF_UPGRADE_STRICT}" || true)"
  if [ -z "$parsed_env_strict" ]; then
    echo "[ERROR] Invalid HONGZHI_SELF_UPGRADE_STRICT value: ${HONGZHI_SELF_UPGRADE_STRICT}" >&2
    exit 2
  fi
  strict_self_upgrade="$parsed_env_strict"
fi

if [ "$requested_subcommand" != "self-upgrade" ] && [ "$strict_self_upgrade" -eq 1 ]; then
  echo "[hongzhi][WARN] --strict-self-upgrade is only effective with subcommand=self-upgrade; ignored" >&2
fi

if ! [[ "$ack_hint_window" =~ ^[0-9]+$ ]]; then
  echo "[ERROR] --ack-hint-window must be a non-negative integer" >&2
  exit 2
fi

has_repo_root=0
repo_arg_index=-1
repo_value_index=-1
user_repo_root=""

has_module_path=0
module_arg_index=-1
module_value_index=-1
module_path_value=""

has_ack=0
ack_arg_index=-1
ack_value_index=-1

for (( i=0; i<${#args[@]}; i++ )); do
  arg="${args[$i]}"
  case "$arg" in
    --repo-root)
      has_repo_root=1
      repo_arg_index="$i"
      next=$((i + 1))
      if [ "$next" -ge "${#args[@]}" ]; then
        echo "[ERROR] Missing value for --repo-root" >&2
        exit 2
      fi
      repo_value_index="$next"
      user_repo_root="${args[$next]}"
      i=$next
      ;;
    --repo-root=*)
      has_repo_root=1
      repo_arg_index="$i"
      user_repo_root="${arg#*=}"
      ;;
    --module-path)
      has_module_path=1
      module_arg_index="$i"
      next=$((i + 1))
      if [ "$next" -ge "${#args[@]}" ]; then
        echo "[ERROR] Missing value for --module-path" >&2
        exit 2
      fi
      module_value_index="$next"
      module_path_value="${args[$next]}"
      i=$next
      ;;
    --module-path=*)
      has_module_path=1
      module_arg_index="$i"
      module_path_value="${arg#*=}"
      ;;
    --ack)
      has_ack=1
      ack_arg_index="$i"
      next=$((i + 1))
      if [ "$next" -ge "${#args[@]}" ]; then
        echo "[ERROR] Missing value for --ack" >&2
        exit 2
      fi
      ack_value_index="$next"
      i=$next
      ;;
    --ack=*)
      has_ack=1
      ack_arg_index="$i"
      ;;
  esac
done

effective_repo_root="$repo_root"
if [ "$has_repo_root" -eq 1 ]; then
  repo_candidate="$user_repo_root"
  if [ -z "$repo_candidate" ]; then
    echo "[ERROR] Empty --repo-root value" >&2
    exit 2
  fi
  if [ "${repo_candidate#/}" = "$repo_candidate" ]; then
    repo_candidate="$PWD/$repo_candidate"
  fi
  if [ ! -d "$repo_candidate" ]; then
    echo "[ERROR] --repo-root is not a directory: $user_repo_root" >&2
    exit 2
  fi
  effective_repo_root="$(cd "$repo_candidate" && pwd -P)"

  if [ "$repo_arg_index" -ge 0 ] && [ "$repo_value_index" -ge 0 ]; then
    args[$repo_value_index]="$effective_repo_root"
  elif [ "$repo_arg_index" -ge 0 ]; then
    args[$repo_arg_index]="--repo-root=$effective_repo_root"
  fi
fi

normalized_module_path=""
if [ "$has_module_path" -eq 1 ]; then
  if [ -z "$module_path_value" ]; then
    echo "[ERROR] Empty --module-path value" >&2
    exit 2
  fi

  module_candidate="$module_path_value"
  if [ "${module_candidate#/}" = "$module_candidate" ]; then
    module_candidate="$effective_repo_root/$module_candidate"
  fi

  if [ ! -d "$module_candidate" ]; then
    echo "[ERROR] --module-path is not an existing directory: $module_path_value" >&2
    exit 2
  fi

  normalized_module_path="$(cd "$module_candidate" && pwd -P)"
  if [ "$module_arg_index" -ge 0 ] && [ "$module_value_index" -ge 0 ]; then
    args[$module_value_index]="$normalized_module_path"
  elif [ "$module_arg_index" -ge 0 ]; then
    args[$module_arg_index]="--module-path=$normalized_module_path"
  fi
fi

effective_policy_path=""
if [ -n "$policy_path_raw" ]; then
  policy_candidate="$policy_path_raw"
  if [ "${policy_candidate#/}" = "$policy_candidate" ]; then
    policy_candidate="$effective_repo_root/$policy_candidate"
  fi
  policy_candidate="$(normalize_path_allow_missing "$policy_candidate")"
  if [ ! -f "$policy_candidate" ]; then
    echo "[ERROR] --policy file not found: $policy_path_raw" >&2
    exit 2
  fi
  effective_policy_path="$policy_candidate"
else
  default_policy="$effective_repo_root/prompt-dsl-system/tools/policy.yaml"
  if [ -f "$default_policy" ]; then
    effective_policy_path="$default_policy"
  fi
fi

if [ -n "$effective_policy_path" ]; then
  runner_global_args+=("--policy" "$effective_policy_path")
fi
if [ "${#policy_overrides[@]}" -gt 0 ]; then
  for ov in "${policy_overrides[@]}"; do
    runner_global_args+=("--policy-override" "$ov")
  done
fi

module_path_observe="NONE"
if [ -n "$normalized_module_path" ]; then
  module_path_observe="$normalized_module_path"
fi
echo "[hongzhi] cmd=$subcommand repo_root=$effective_repo_root module_path=$module_path_observe"
if [ "$requested_subcommand" = "self-upgrade" ]; then
  echo "[hongzhi] cmd_alias=self-upgrade->run pipeline=prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_kit_self_upgrade.md"
fi
if [ "$no_snapshot_requested" -eq 1 ] && { [ "$subcommand" = "apply-move" ] || [ "$subcommand" = "resolve-move-conflicts" ] || [ "$subcommand" = "apply-followup-fixes" ]; }; then
  echo "[hongzhi][WARN] snapshot disabled by --no-snapshot; apply will proceed without automatic restore point." >&2
fi

if [ "$subcommand" = "run" ] && [ "$has_module_path" -eq 0 ]; then
  if [ "${HONGZHI_ALLOW_RUN_WITHOUT_MODULE_PATH:-0}" = "1" ]; then
    echo "[hongzhi][WARN] running without module-path is risky; guard will restrict changes to prompt-dsl-system/**"
  else
    echo "module-path is required for run (company guardrail)" >&2
    echo "example: ./prompt-dsl-system/tools/run.sh run -r . -m <MODULE_PATH> --pipeline <PIPELINE>" >&2
    exit 2
  fi
fi

if [ "$ack_latest" -eq 1 ] && [ -z "$ack_file_raw" ]; then
  if [ "$subcommand" = "apply-move" ] || [ "$subcommand" = "resolve-move-conflicts" ] || [ "$subcommand" = "apply-followup-fixes" ]; then
    ack_file_raw="$(resolve_output_token_json_path "$effective_repo_root" "${args[@]-}")"
  else
    ack_file_raw="$TOKEN_JSON_REL_DEFAULT"
  fi
fi

ack_file_abs=""
if [ -n "$ack_file_raw" ]; then
  if [ "${ack_file_raw#/}" = "$ack_file_raw" ]; then
    ack_file_abs="$effective_repo_root/$ack_file_raw"
  else
    ack_file_abs="$ack_file_raw"
  fi
  ack_file_abs="$(normalize_path_allow_missing "$ack_file_abs")"
fi

if [ "$subcommand" != "run" ] && [ "$subcommand" != "apply-move" ] && [ "$subcommand" != "resolve-move-conflicts" ] && [ "$subcommand" != "apply-followup-fixes" ] && [ "$ack_latest" -eq 1 -o -n "$ack_file_raw" ]; then
  echo "[hongzhi][WARN] --ack-latest/--ack-file is only used by run/apply-move/resolve-move-conflicts/apply-followup-fixes; ignored for cmd=$subcommand" >&2
fi

if { [ "$subcommand" = "run" ] || [ "$subcommand" = "apply-move" ] || [ "$subcommand" = "resolve-move-conflicts" ] || [ "$subcommand" = "apply-followup-fixes" ]; } && [ "$has_ack" -eq 0 ] && { [ "$ack_latest" -eq 1 ] || [ -n "$ack_file_raw" ]; }; then
  if [ -z "$ack_file_abs" ]; then
    echo "[ERROR] Failed to resolve ack file path" >&2
    exit 2
  fi
  if [ ! -f "$ack_file_abs" ]; then
    echo "[ERROR] ACK token file not found: $ack_file_abs" >&2
    exit 2
  fi

  set +e
  ack_token="$(read_ack_token_from_json "$ack_file_abs")"
  ack_rc=$?
  set -e
  if [ "$ack_rc" -ne 0 ] || [ -z "$ack_token" ]; then
    echo "[ERROR] Failed to read ACK token from: $ack_file_abs" >&2
    exit 2
  fi

  args+=("--ack" "$ack_token")
  has_ack=1
fi

if [ "$subcommand" = "run" ] || [ "$subcommand" = "apply-move" ] || [ "$subcommand" = "apply-followup-fixes" ]; then
  ack_source="none"
  if [ "$ack_latest" -eq 1 ]; then
    ack_source="ack-latest"
  elif [ -n "$ack_file_raw" ]; then
    ack_source="ack-file"
  elif [ "$has_ack" -eq 1 ]; then
    ack_source="ack"
  fi
  args+=("--ack-source" "$ack_source")
fi

if [ "${#args[@]}" -gt 0 ]; then
  invoke_args=("${args[@]}")
else
  invoke_args=()
fi
if [ "$has_repo_root" -eq 0 ]; then
  if [ "${#invoke_args[@]}" -gt 0 ]; then
    invoke_args=("--repo-root" "$effective_repo_root" "${invoke_args[@]}")
  else
    invoke_args=("--repo-root" "$effective_repo_root")
  fi
fi

if [ "$subcommand" = "rollback" ]; then
  if [ ! -f "$ROLLBACK_HELPER_PATH" ]; then
    echo "[ERROR] rollback_helper.py not found: $ROLLBACK_HELPER_PATH" >&2
    exit 2
  fi
  set +e
  run_rollback_once "${invoke_args[@]-}"
  rollback_rc=$?
  set -e
  exit "$rollback_rc"
fi

if [ "$subcommand" = "selfcheck" ]; then
  SELFCHECK_SCRIPT="${SCRIPT_DIR}/kit_selfcheck.py"
  if [ ! -f "$SELFCHECK_SCRIPT" ]; then
    echo "[ERROR] kit_selfcheck.py not found: $SELFCHECK_SCRIPT" >&2
    exit 2
  fi
  set +e
  "$PYTHON_BIN" "$SELFCHECK_SCRIPT" "${invoke_args[@]-}"
  selfcheck_rc=$?
  set -e
  exit "$selfcheck_rc"
fi

if [ "$subcommand" = "intent" ]; then
  INTENT_ROUTER_SCRIPT="${SCRIPT_DIR}/intent_router.py"
  if [ ! -f "$INTENT_ROUTER_SCRIPT" ]; then
    echo "[ERROR] intent_router.py not found: $INTENT_ROUTER_SCRIPT" >&2
    exit 2
  fi
  set +e
  "$PYTHON_BIN" "$INTENT_ROUTER_SCRIPT" "${invoke_args[@]-}"
  intent_rc=$?
  set -e
  exit "$intent_rc"
fi

if [ "$requested_subcommand" = "self-upgrade" ] && [ "$strict_self_upgrade" -eq 1 ]; then
  echo "[hongzhi][self-upgrade][strict] preflight start (selfcheck(contract) -> selfcheck_gate -> selfcheck_freshness -> kit_integrity -> pipeline_trust -> pipeline_trust_coverage -> baseline_provenance -> governance_consistency -> tool_syntax -> mutation_guard -> performance_guard -> dual_approval(opt) -> lint -> audit -> validate)"

  SELFCHECK_SCRIPT="${SCRIPT_DIR}/kit_selfcheck.py"
  SELFCHECK_GATE_SCRIPT="${SCRIPT_DIR}/kit_selfcheck_gate.py"
  SELFCHECK_FRESHNESS_SCRIPT="${SCRIPT_DIR}/kit_selfcheck_freshness_gate.py"
  KIT_INTEGRITY_SCRIPT="${SCRIPT_DIR}/kit_integrity_guard.py"
  PIPELINE_TRUST_SCRIPT="${SCRIPT_DIR}/pipeline_trust_guard.py"
  PIPELINE_TRUST_COVERAGE_SCRIPT="${SCRIPT_DIR}/pipeline_trust_coverage_guard.py"
  BASELINE_PROVENANCE_SCRIPT="${SCRIPT_DIR}/baseline_provenance_guard.py"
  GOVERNANCE_CONSISTENCY_SCRIPT="${SCRIPT_DIR}/governance_consistency_guard.py"
  TOOL_SYNTAX_SCRIPT="${SCRIPT_DIR}/tool_syntax_guard.py"
  MUTATION_GUARD_SCRIPT="${SCRIPT_DIR}/gate_mutation_guard.py"
  PERFORMANCE_GUARD_SCRIPT="${SCRIPT_DIR}/performance_budget_guard.py"
  DUAL_APPROVAL_SCRIPT="${SCRIPT_DIR}/kit_dual_approval_guard.py"
  VALIDATOR_SCRIPT="${SCRIPT_DIR}/contract_validator.py"
  LINT_SCRIPT="${SCRIPT_DIR}/pipeline_contract_lint.py"
  AUDIT_SCRIPT="${SCRIPT_DIR}/skill_template_audit.py"

  if [ ! -f "$SELFCHECK_SCRIPT" ]; then
    echo "[ERROR] missing strict gate dependency: $SELFCHECK_SCRIPT" >&2
    exit 2
  fi
  if [ ! -f "$VALIDATOR_SCRIPT" ]; then
    echo "[ERROR] missing strict gate dependency: $VALIDATOR_SCRIPT" >&2
    exit 2
  fi
  if [ ! -f "$SELFCHECK_GATE_SCRIPT" ]; then
    echo "[ERROR] missing strict gate dependency: $SELFCHECK_GATE_SCRIPT" >&2
    exit 2
  fi
  if [ ! -f "$SELFCHECK_FRESHNESS_SCRIPT" ]; then
    echo "[ERROR] missing strict gate dependency: $SELFCHECK_FRESHNESS_SCRIPT" >&2
    exit 2
  fi
  if [ ! -f "$KIT_INTEGRITY_SCRIPT" ]; then
    echo "[ERROR] missing strict gate dependency: $KIT_INTEGRITY_SCRIPT" >&2
    exit 2
  fi
  if [ ! -f "$PIPELINE_TRUST_SCRIPT" ]; then
    echo "[ERROR] missing strict gate dependency: $PIPELINE_TRUST_SCRIPT" >&2
    exit 2
  fi
  if [ ! -f "$PIPELINE_TRUST_COVERAGE_SCRIPT" ]; then
    echo "[ERROR] missing strict gate dependency: $PIPELINE_TRUST_COVERAGE_SCRIPT" >&2
    exit 2
  fi
  if [ ! -f "$BASELINE_PROVENANCE_SCRIPT" ]; then
    echo "[ERROR] missing strict gate dependency: $BASELINE_PROVENANCE_SCRIPT" >&2
    exit 2
  fi
  if [ ! -f "$GOVERNANCE_CONSISTENCY_SCRIPT" ]; then
    echo "[ERROR] missing strict gate dependency: $GOVERNANCE_CONSISTENCY_SCRIPT" >&2
    exit 2
  fi
  if [ ! -f "$TOOL_SYNTAX_SCRIPT" ]; then
    echo "[ERROR] missing strict gate dependency: $TOOL_SYNTAX_SCRIPT" >&2
    exit 2
  fi
  if [ ! -f "$MUTATION_GUARD_SCRIPT" ]; then
    echo "[ERROR] missing strict gate dependency: $MUTATION_GUARD_SCRIPT" >&2
    exit 2
  fi
  if [ ! -f "$PERFORMANCE_GUARD_SCRIPT" ]; then
    echo "[ERROR] missing strict gate dependency: $PERFORMANCE_GUARD_SCRIPT" >&2
    exit 2
  fi
  if [ ! -f "$DUAL_APPROVAL_SCRIPT" ]; then
    echo "[ERROR] missing strict gate dependency: $DUAL_APPROVAL_SCRIPT" >&2
    exit 2
  fi
  if [ ! -f "$LINT_SCRIPT" ]; then
    echo "[ERROR] missing strict gate dependency: $LINT_SCRIPT" >&2
    exit 2
  fi
  if [ ! -f "$AUDIT_SCRIPT" ]; then
    echo "[ERROR] missing strict gate dependency: $AUDIT_SCRIPT" >&2
    exit 2
  fi

  strict_schema_v1="${SCRIPT_DIR}/contract_schema_v1.json"
  strict_schema_v2="${SCRIPT_DIR}/contract_schema_v2.json"
  strict_schema="$strict_schema_v1"
  if [ -f "$strict_schema_v2" ]; then
    strict_schema="$strict_schema_v2"
  fi

  strict_tmp_json="/tmp/hz_selfupgrade_${$}_selfcheck.json"
  strict_tmp_md="/tmp/hz_selfupgrade_${$}_selfcheck.md"
  strict_tmp_gate_json="/tmp/hz_selfupgrade_${$}_selfcheck_gate.json"
  strict_tmp_fresh_json="/tmp/hz_selfupgrade_${$}_selfcheck_freshness.json"
  strict_tmp_integrity_json="/tmp/hz_selfupgrade_${$}_kit_integrity.json"
  strict_tmp_trust_json="/tmp/hz_selfupgrade_${$}_pipeline_trust.json"
  strict_tmp_trust_coverage_json="/tmp/hz_selfupgrade_${$}_pipeline_trust_coverage.json"
  strict_tmp_provenance_json="/tmp/hz_selfupgrade_${$}_baseline_provenance.json"
  strict_tmp_consistency_json="/tmp/hz_selfupgrade_${$}_governance_consistency.json"
  strict_tmp_syntax_json="/tmp/hz_selfupgrade_${$}_tool_syntax.json"
  strict_tmp_mutation_json="/tmp/hz_selfupgrade_${$}_mutation_guard.json"
  strict_tmp_perf_json="/tmp/hz_selfupgrade_${$}_performance_guard.json"
  strict_tmp_dual_json="/tmp/hz_selfupgrade_${$}_dual_approval.json"
  cleanup_strict_temp() {
    rm -f "$strict_tmp_json" "$strict_tmp_md" "$strict_tmp_gate_json" \
      "$strict_tmp_fresh_json" "$strict_tmp_integrity_json" "$strict_tmp_trust_json" \
      "$strict_tmp_trust_coverage_json" "$strict_tmp_provenance_json" \
      "$strict_tmp_consistency_json" "$strict_tmp_syntax_json" "$strict_tmp_mutation_json" "$strict_tmp_perf_json" \
      "$strict_tmp_dual_json" >/dev/null 2>&1 || true
  }
  strict_validator_args=(--stdin --schema "$strict_schema")
  if [ "$strict_schema" = "$strict_schema_v2" ] && [ -f "$strict_schema_v1" ]; then
    strict_validator_args+=(--baseline-schema "$strict_schema_v1")
  fi
  echo "[hongzhi][self-upgrade][strict] contract_schema=$(basename "$strict_schema")"

  set +e
  "$PYTHON_BIN" "$SELFCHECK_SCRIPT" --repo-root "$effective_repo_root" --out-json "$strict_tmp_json" --out-md "$strict_tmp_md" \
    | "$PYTHON_BIN" "$VALIDATOR_SCRIPT" "${strict_validator_args[@]}"
  strict_selfcheck_rc=$?
  set -e
  if [ "$strict_selfcheck_rc" -ne 0 ]; then
    cleanup_strict_temp
    echo "[hongzhi][self-upgrade][strict] FAIL: selfcheck contract validation failed (exit=$strict_selfcheck_rc)" >&2
    exit "$strict_selfcheck_rc"
  fi

  strict_selfcheck_min_level="${HONGZHI_SELFCHECK_MIN_LEVEL:-high}"
  strict_selfcheck_min_score="${HONGZHI_SELFCHECK_MIN_SCORE:-0.85}"
  strict_selfcheck_max_low_dims="${HONGZHI_SELFCHECK_MAX_LOW_DIMS:-0}"
  strict_selfcheck_required_dims="${HONGZHI_SELFCHECK_REQUIRED_DIMS:-}"
  echo "[hongzhi][self-upgrade][strict] selfcheck_gate thresholds: level>=$strict_selfcheck_min_level score>=$strict_selfcheck_min_score low_dims<=$strict_selfcheck_max_low_dims"
  if [ -n "$strict_selfcheck_required_dims" ]; then
    echo "[hongzhi][self-upgrade][strict] selfcheck_gate required_dims=$strict_selfcheck_required_dims"
  fi
  strict_selfcheck_gate_args=(
    --report-json "$strict_tmp_json"
    --min-overall-score "$strict_selfcheck_min_score"
    --min-overall-level "$strict_selfcheck_min_level"
    --max-low-dimensions "$strict_selfcheck_max_low_dims"
    --out-json "$strict_tmp_gate_json"
  )
  if [ -n "$strict_selfcheck_required_dims" ]; then
    strict_selfcheck_gate_args+=(--required-dimensions "$strict_selfcheck_required_dims")
  fi
  set +e
  "$PYTHON_BIN" "$SELFCHECK_GATE_SCRIPT" "${strict_selfcheck_gate_args[@]}"
  strict_selfcheck_gate_rc=$?
  set -e
  if [ "$strict_selfcheck_gate_rc" -ne 0 ]; then
    cleanup_strict_temp
    echo "[hongzhi][self-upgrade][strict] FAIL: selfcheck quality gate failed (exit=$strict_selfcheck_gate_rc)" >&2
    exit "$strict_selfcheck_gate_rc"
  fi

  strict_selfcheck_max_age="${HONGZHI_SELFCHECK_MAX_AGE_SECONDS:-900}"
  strict_selfcheck_require_head="${HONGZHI_SELFCHECK_REQUIRE_GIT_HEAD:-0}"
  echo "[hongzhi][self-upgrade][strict] selfcheck_freshness max_age_seconds=$strict_selfcheck_max_age require_git_head=$strict_selfcheck_require_head"
  set +e
  "$PYTHON_BIN" "$SELFCHECK_FRESHNESS_SCRIPT" \
    --report-json "$strict_tmp_json" \
    --repo-root "$effective_repo_root" \
    --max-age-seconds "$strict_selfcheck_max_age" \
    --require-git-head "$strict_selfcheck_require_head" \
    --out-json "$strict_tmp_fresh_json"
  strict_selfcheck_fresh_rc=$?
  set -e
  if [ "$strict_selfcheck_fresh_rc" -ne 0 ]; then
    cleanup_strict_temp
    echo "[hongzhi][self-upgrade][strict] FAIL: selfcheck freshness gate failed (exit=$strict_selfcheck_fresh_rc)" >&2
    exit "$strict_selfcheck_fresh_rc"
  fi

  strict_sign_key_env_name="${HONGZHI_BASELINE_SIGN_KEY_ENV:-HONGZHI_BASELINE_SIGN_KEY}"
  if ! [[ "$strict_sign_key_env_name" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
    cleanup_strict_temp
    echo "[hongzhi][self-upgrade][strict] FAIL: invalid HONGZHI_BASELINE_SIGN_KEY_ENV=$strict_sign_key_env_name" >&2
    exit 2
  fi
  strict_sign_key_value="${!strict_sign_key_env_name:-}"

  strict_require_hmac_raw="${HONGZHI_BASELINE_REQUIRE_HMAC:-auto}"
  strict_require_hmac=0
  if [ -z "$strict_require_hmac_raw" ] || [ "$strict_require_hmac_raw" = "auto" ]; then
    if [ -n "$strict_sign_key_value" ]; then
      strict_require_hmac=1
    fi
  else
    strict_require_hmac="$(parse_bool "$strict_require_hmac_raw" || true)"
    if [ -z "$strict_require_hmac" ]; then
      cleanup_strict_temp
      echo "[hongzhi][self-upgrade][strict] FAIL: invalid HONGZHI_BASELINE_REQUIRE_HMAC=$strict_require_hmac_raw" >&2
      exit 2
    fi
  fi
  if [ "$strict_require_hmac" -eq 1 ] && [ -z "$strict_sign_key_value" ]; then
    cleanup_strict_temp
    echo "[hongzhi][self-upgrade][strict] FAIL: require_hmac=1 but sign key env '$strict_sign_key_env_name' is empty" >&2
    exit 2
  fi

  strict_integrity_manifest="${HONGZHI_KIT_INTEGRITY_MANIFEST:-prompt-dsl-system/tools/kit_integrity_manifest.json}"
  if [ "${strict_integrity_manifest#/}" = "$strict_integrity_manifest" ]; then
    strict_integrity_manifest="$effective_repo_root/$strict_integrity_manifest"
  fi
  strict_integrity_manifest="$(normalize_path_allow_missing "$strict_integrity_manifest")"
  strict_integrity_strict_set="${HONGZHI_KIT_INTEGRITY_STRICT_SET:-1}"
  echo "[hongzhi][self-upgrade][strict] baseline_signature require_hmac=$strict_require_hmac sign_key_env=$strict_sign_key_env_name sign_key_present=$([ -n "$strict_sign_key_value" ] && echo 1 || echo 0)"
  echo "[hongzhi][self-upgrade][strict] kit_integrity manifest=$strict_integrity_manifest strict_source_set=$strict_integrity_strict_set"
  set +e
  "$PYTHON_BIN" "$KIT_INTEGRITY_SCRIPT" verify \
    --repo-root "$effective_repo_root" \
    --manifest "$strict_integrity_manifest" \
    --strict-source-set "$strict_integrity_strict_set" \
    --sign-key-env "$strict_sign_key_env_name" \
    --require-hmac "$strict_require_hmac" \
    --out-json "$strict_tmp_integrity_json"
  strict_integrity_rc=$?
  set -e
  if [ "$strict_integrity_rc" -ne 0 ]; then
    cleanup_strict_temp
    echo "[hongzhi][self-upgrade][strict] FAIL: kit integrity gate failed (exit=$strict_integrity_rc)" >&2
    exit "$strict_integrity_rc"
  fi

  strict_pipeline_arg=""
  for (( i=0; i<${#args[@]}; i++ )); do
    arg="${args[$i]}"
    case "$arg" in
      --pipeline)
        next=$((i + 1))
        if [ "$next" -lt "${#args[@]}" ]; then
          strict_pipeline_arg="${args[$next]}"
          i=$next
        fi
        ;;
      --pipeline=*)
        strict_pipeline_arg="${arg#*=}"
        ;;
    esac
  done
  if [ -z "$strict_pipeline_arg" ]; then
    strict_pipeline_arg="prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_kit_self_upgrade.md"
  fi
  strict_pipeline_abs="$strict_pipeline_arg"
  if [ "${strict_pipeline_abs#/}" = "$strict_pipeline_abs" ]; then
    strict_pipeline_abs="$effective_repo_root/$strict_pipeline_abs"
  fi
  strict_pipeline_abs="$(normalize_path_allow_missing "$strict_pipeline_abs")"

  strict_trust_whitelist="${HONGZHI_PIPELINE_TRUST_WHITELIST:-prompt-dsl-system/tools/pipeline_trust_whitelist.json}"
  if [ "${strict_trust_whitelist#/}" = "$strict_trust_whitelist" ]; then
    strict_trust_whitelist="$effective_repo_root/$strict_trust_whitelist"
  fi
  strict_trust_whitelist="$(normalize_path_allow_missing "$strict_trust_whitelist")"
  strict_trust_strict_set="${HONGZHI_PIPELINE_TRUST_STRICT_SET:-1}"
  strict_trust_require_active="${HONGZHI_PIPELINE_TRUST_REQUIRE_ACTIVE:-1}"
  echo "[hongzhi][self-upgrade][strict] pipeline_trust whitelist=$strict_trust_whitelist strict_source_set=$strict_trust_strict_set require_active=$strict_trust_require_active"
  set +e
  "$PYTHON_BIN" "$PIPELINE_TRUST_SCRIPT" verify \
    --repo-root "$effective_repo_root" \
    --pipeline "$strict_pipeline_abs" \
    --whitelist "$strict_trust_whitelist" \
    --strict-source-set "$strict_trust_strict_set" \
    --require-active "$strict_trust_require_active" \
    --sign-key-env "$strict_sign_key_env_name" \
    --require-hmac "$strict_require_hmac" \
    --out-json "$strict_tmp_trust_json"
  strict_trust_rc=$?
  set -e
  if [ "$strict_trust_rc" -ne 0 ]; then
    cleanup_strict_temp
    echo "[hongzhi][self-upgrade][strict] FAIL: pipeline trust gate failed (exit=$strict_trust_rc)" >&2
    exit "$strict_trust_rc"
  fi

  strict_trust_coverage_strict_set="${HONGZHI_PIPELINE_TRUST_COVERAGE_STRICT_SET:-1}"
  strict_trust_coverage_require_active="${HONGZHI_PIPELINE_TRUST_COVERAGE_REQUIRE_ACTIVE:-1}"
  echo "[hongzhi][self-upgrade][strict] pipeline_trust_coverage strict_source_set=$strict_trust_coverage_strict_set require_active=$strict_trust_coverage_require_active"
  set +e
  "$PYTHON_BIN" "$PIPELINE_TRUST_COVERAGE_SCRIPT" \
    --repo-root "$effective_repo_root" \
    --whitelist "$strict_trust_whitelist" \
    --strict-source-set "$strict_trust_coverage_strict_set" \
    --require-active "$strict_trust_coverage_require_active" \
    --sign-key-env "$strict_sign_key_env_name" \
    --require-hmac "$strict_require_hmac" \
    --out-json "$strict_tmp_trust_coverage_json"
  strict_trust_coverage_rc=$?
  set -e
  if [ "$strict_trust_coverage_rc" -ne 0 ]; then
    cleanup_strict_temp
    echo "[hongzhi][self-upgrade][strict] FAIL: pipeline trust coverage gate failed (exit=$strict_trust_coverage_rc)" >&2
    exit "$strict_trust_coverage_rc"
  fi

  strict_provenance_file="${HONGZHI_BASELINE_PROVENANCE_FILE:-prompt-dsl-system/tools/baseline_provenance.json}"
  if [ "${strict_provenance_file#/}" = "$strict_provenance_file" ]; then
    strict_provenance_file="$effective_repo_root/$strict_provenance_file"
  fi
  strict_provenance_file="$(normalize_path_allow_missing "$strict_provenance_file")"
  strict_provenance_strict_set="${HONGZHI_BASELINE_PROVENANCE_STRICT_SET:-1}"
  strict_provenance_max_age="${HONGZHI_BASELINE_PROVENANCE_MAX_AGE_SECONDS:-0}"
  strict_provenance_require_git="${HONGZHI_BASELINE_PROVENANCE_REQUIRE_GIT:-0}"
  echo "[hongzhi][self-upgrade][strict] baseline_provenance file=$strict_provenance_file strict_source_set=$strict_provenance_strict_set max_age_seconds=$strict_provenance_max_age require_git_head=$strict_provenance_require_git"
  set +e
  "$PYTHON_BIN" "$BASELINE_PROVENANCE_SCRIPT" verify \
    --repo-root "$effective_repo_root" \
    --provenance "$strict_provenance_file" \
    --strict-source-set "$strict_provenance_strict_set" \
    --max-age-seconds "$strict_provenance_max_age" \
    --require-git-head "$strict_provenance_require_git" \
    --sign-key-env "$strict_sign_key_env_name" \
    --require-hmac "$strict_require_hmac" \
    --out-json "$strict_tmp_provenance_json"
  strict_provenance_rc=$?
  set -e
  if [ "$strict_provenance_rc" -ne 0 ]; then
    cleanup_strict_temp
    echo "[hongzhi][self-upgrade][strict] FAIL: baseline provenance gate failed (exit=$strict_provenance_rc)" >&2
    exit "$strict_provenance_rc"
  fi

  strict_governance_require_met="${HONGZHI_GOVERNANCE_REQUIRE_MET_STATUS:-1}"
  strict_governance_tail_window="${HONGZHI_GOVERNANCE_FACT_TAIL_WINDOW:-17}"
  echo "[hongzhi][self-upgrade][strict] governance_consistency require_met=$strict_governance_require_met fact_tail_window=$strict_governance_tail_window"
  set +e
  "$PYTHON_BIN" "$GOVERNANCE_CONSISTENCY_SCRIPT" \
    --repo-root "$effective_repo_root" \
    --require-met-status "$strict_governance_require_met" \
    --fact-tail-window "$strict_governance_tail_window" \
    --out-json "$strict_tmp_consistency_json"
  strict_governance_rc=$?
  set -e
  if [ "$strict_governance_rc" -ne 0 ]; then
    cleanup_strict_temp
    echo "[hongzhi][self-upgrade][strict] FAIL: governance consistency gate failed (exit=$strict_governance_rc)" >&2
    exit "$strict_governance_rc"
  fi

  strict_tool_syntax_set="${HONGZHI_TOOL_SYNTAX_STRICT_SET:-1}"
  echo "[hongzhi][self-upgrade][strict] tool_syntax strict_source_set=$strict_tool_syntax_set"
  set +e
  "$PYTHON_BIN" "$TOOL_SYNTAX_SCRIPT" \
    --repo-root "$effective_repo_root" \
    --strict-source-set "$strict_tool_syntax_set" \
    --out-json "$strict_tmp_syntax_json"
  strict_tool_syntax_rc=$?
  set -e
  if [ "$strict_tool_syntax_rc" -ne 0 ]; then
    cleanup_strict_temp
    echo "[hongzhi][self-upgrade][strict] FAIL: tool syntax gate failed (exit=$strict_tool_syntax_rc)" >&2
    exit "$strict_tool_syntax_rc"
  fi

  strict_mutation_enforce_raw="${HONGZHI_MUTATION_GUARD_ENFORCE:-1}"
  strict_mutation_enforce="$(parse_bool "$strict_mutation_enforce_raw" || true)"
  if [ -z "$strict_mutation_enforce" ]; then
    cleanup_strict_temp
    echo "[hongzhi][self-upgrade][strict] FAIL: invalid HONGZHI_MUTATION_GUARD_ENFORCE=$strict_mutation_enforce_raw" >&2
    exit 2
  fi
  if [ "$strict_mutation_enforce" -eq 1 ]; then
    echo "[hongzhi][self-upgrade][strict] mutation_guard enforce=1"
    set +e
    "$PYTHON_BIN" "$MUTATION_GUARD_SCRIPT" --repo-root "$effective_repo_root" --out-json "$strict_tmp_mutation_json"
    strict_mutation_rc=$?
    set -e
    if [ "$strict_mutation_rc" -ne 0 ]; then
      cleanup_strict_temp
      echo "[hongzhi][self-upgrade][strict] FAIL: mutation guard failed (exit=$strict_mutation_rc)" >&2
      exit "$strict_mutation_rc"
    fi
  else
    echo "[hongzhi][self-upgrade][strict] mutation_guard enforce=0 (skipped)"
  fi

  strict_perf_enforce_raw="${HONGZHI_PERFORMANCE_GUARD_ENFORCE:-1}"
  strict_perf_enforce="$(parse_bool "$strict_perf_enforce_raw" || true)"
  if [ -z "$strict_perf_enforce" ]; then
    cleanup_strict_temp
    echo "[hongzhi][self-upgrade][strict] FAIL: invalid HONGZHI_PERFORMANCE_GUARD_ENFORCE=$strict_perf_enforce_raw" >&2
    exit 2
  fi
  if [ "$strict_perf_enforce" -eq 1 ]; then
    strict_perf_selfcheck_max="${HONGZHI_PERF_MAX_SELFCHECK_SECONDS:-15}"
    strict_perf_governance_max="${HONGZHI_PERF_MAX_GOVERNANCE_SECONDS:-10}"
    strict_perf_syntax_max="${HONGZHI_PERF_MAX_SYNTAX_SECONDS:-25}"
    strict_perf_trust_cov_max="${HONGZHI_PERF_MAX_TRUST_COVERAGE_SECONDS:-10}"
    strict_perf_total_max="${HONGZHI_PERF_MAX_TOTAL_SECONDS:-70}"
    strict_perf_trend_enforce="${HONGZHI_PERF_TREND_ENFORCE:-0}"
    strict_perf_history_file="${HONGZHI_PERF_TREND_HISTORY_FILE:-prompt-dsl-system/tools/performance_history.jsonl}"
    strict_perf_history_window="${HONGZHI_PERF_TREND_WINDOW:-30}"
    strict_perf_trend_min_samples="${HONGZHI_PERF_TREND_MIN_SAMPLES:-5}"
    strict_perf_trend_max_ratio="${HONGZHI_PERF_TREND_MAX_RATIO:-1.8}"
    strict_perf_history_write="${HONGZHI_PERF_HISTORY_WRITE:-1}"
    echo "[hongzhi][self-upgrade][strict] performance_guard enforce=1 max_total_seconds=$strict_perf_total_max trend_enforce=$strict_perf_trend_enforce"
    set +e
    "$PYTHON_BIN" "$PERFORMANCE_GUARD_SCRIPT" \
      --repo-root "$effective_repo_root" \
      --max-selfcheck-seconds "$strict_perf_selfcheck_max" \
      --max-governance-seconds "$strict_perf_governance_max" \
      --max-syntax-seconds "$strict_perf_syntax_max" \
      --max-trust-coverage-seconds "$strict_perf_trust_cov_max" \
      --max-total-seconds "$strict_perf_total_max" \
      --trend-enforce "$strict_perf_trend_enforce" \
      --history-file "$strict_perf_history_file" \
      --history-window "$strict_perf_history_window" \
      --trend-min-samples "$strict_perf_trend_min_samples" \
      --trend-max-ratio "$strict_perf_trend_max_ratio" \
      --history-write "$strict_perf_history_write" \
      --out-json "$strict_tmp_perf_json"
    strict_perf_rc=$?
    set -e
    if [ "$strict_perf_rc" -ne 0 ]; then
      cleanup_strict_temp
      echo "[hongzhi][self-upgrade][strict] FAIL: performance guard failed (exit=$strict_perf_rc)" >&2
      exit "$strict_perf_rc"
    fi
  else
    echo "[hongzhi][self-upgrade][strict] performance_guard enforce=0 (skipped)"
  fi

  strict_dual_approval_raw="${HONGZHI_BASELINE_DUAL_APPROVAL:-0}"
  strict_dual_approval="$(parse_bool "$strict_dual_approval_raw" || true)"
  if [ -z "$strict_dual_approval" ]; then
    cleanup_strict_temp
    echo "[hongzhi][self-upgrade][strict] FAIL: invalid HONGZHI_BASELINE_DUAL_APPROVAL=$strict_dual_approval_raw" >&2
    exit 2
  fi
  if [ "$strict_dual_approval" -eq 1 ]; then
    strict_approval_file="${HONGZHI_BASELINE_APPROVAL_FILE:-prompt-dsl-system/tools/baseline_dual_approval.json}"
    if [ "${strict_approval_file#/}" = "$strict_approval_file" ]; then
      strict_approval_file="$effective_repo_root/$strict_approval_file"
    fi
    strict_approval_file="$(normalize_path_allow_missing "$strict_approval_file")"
    strict_approval_watch_files="${HONGZHI_BASELINE_APPROVAL_WATCH_FILES:-prompt-dsl-system/tools/kit_integrity_manifest.json,prompt-dsl-system/tools/pipeline_trust_whitelist.json}"
    strict_approval_required="${HONGZHI_BASELINE_APPROVAL_REQUIRED_COUNT:-2}"
    strict_approval_enforce_always="${HONGZHI_BASELINE_APPROVAL_ENFORCE_ALWAYS:-0}"
    strict_approval_require_git="${HONGZHI_BASELINE_APPROVAL_REQUIRE_GIT:-0}"
    echo "[hongzhi][self-upgrade][strict] dual_approval enabled watch_files=$strict_approval_watch_files required=$strict_approval_required approval_file=$strict_approval_file"
    set +e
    "$PYTHON_BIN" "$DUAL_APPROVAL_SCRIPT" \
      --repo-root "$effective_repo_root" \
      --watch-files "$strict_approval_watch_files" \
      --approval-file "$strict_approval_file" \
      --required-approvers "$strict_approval_required" \
      --enforce-always "$strict_approval_enforce_always" \
      --require-git "$strict_approval_require_git" \
      --out-json "$strict_tmp_dual_json"
    strict_dual_rc=$?
    set -e
    if [ "$strict_dual_rc" -ne 0 ]; then
      cleanup_strict_temp
      echo "[hongzhi][self-upgrade][strict] FAIL: dual approval gate failed (exit=$strict_dual_rc)" >&2
      exit "$strict_dual_rc"
    fi
  fi

  set +e
  "$PYTHON_BIN" "$LINT_SCRIPT" --repo-root "$effective_repo_root" --fail-on-empty
  strict_lint_rc=$?
  set -e
  if [ "$strict_lint_rc" -ne 0 ]; then
    cleanup_strict_temp
    echo "[hongzhi][self-upgrade][strict] FAIL: pipeline_contract_lint failed (exit=$strict_lint_rc)" >&2
    exit "$strict_lint_rc"
  fi

  set +e
  "$PYTHON_BIN" "$AUDIT_SCRIPT" --repo-root "$effective_repo_root" --scope all --fail-on-empty
  strict_audit_rc=$?
  set -e
  if [ "$strict_audit_rc" -ne 0 ]; then
    cleanup_strict_temp
    echo "[hongzhi][self-upgrade][strict] FAIL: skill_template_audit failed (exit=$strict_audit_rc)" >&2
    exit "$strict_audit_rc"
  fi

  previous_validate_strict="${HONGZHI_VALIDATE_STRICT:-}"
  export HONGZHI_VALIDATE_STRICT=1
  strict_validate_args=(--repo-root "$effective_repo_root")
  if [ -n "$normalized_module_path" ]; then
    strict_validate_args+=(--module-path "$normalized_module_path")
  fi
  set +e
  run_runner_once "validate" "${strict_validate_args[@]}"
  strict_validate_rc=$?
  set -e
  if [ -n "$previous_validate_strict" ]; then
    export HONGZHI_VALIDATE_STRICT="$previous_validate_strict"
  else
    unset HONGZHI_VALIDATE_STRICT || true
  fi
  if [ "$strict_validate_rc" -ne 0 ]; then
    cleanup_strict_temp
    echo "[hongzhi][self-upgrade][strict] FAIL: validate gate failed (exit=$strict_validate_rc)" >&2
    exit "$strict_validate_rc"
  fi

  cleanup_strict_temp
  echo "[hongzhi][self-upgrade][strict] preflight PASS"
fi

set +e
run_runner_once "$subcommand" "${invoke_args[@]-}"
runner_rc=$?
set -e

if [ "$subcommand" = "validate" ] && [ "$runner_rc" -eq 0 ]; then
  health_report_disabled=0
  health_runbook_disabled=0
  audit_rc=-1
  lint_rc=-1
  replay_rc=-1
  template_guard_rc=-1
  governance_consistency_rc=-1
  tool_syntax_rc=-1
  trust_coverage_rc=-1
  provenance_rc=-1
  mutation_rc=-1
  performance_rc=-1
  for arg in "${invoke_args[@]-}"; do
    if [ "$arg" = "--no-health-report" ]; then
      health_report_disabled=1
    fi
    if [ "$arg" = "--no-health-runbook" ]; then
      health_runbook_disabled=1
    fi
  done
  if [ "$health_report_disabled" -eq 0 ]; then
    echo "[hongzhi] health_report=prompt-dsl-system/tools/health_report.md"
  fi
  if [ "$health_runbook_disabled" -eq 0 ]; then
    echo "[hongzhi] health_runbook=prompt-dsl-system/tools/health_runbook.md"
  fi

  # Strict mode: HONGZHI_VALIDATE_STRICT=1 enables --fail-on-empty + VCS guard
  STRICT_FLAG=""
  if [ "${HONGZHI_VALIDATE_STRICT:-0}" = "1" ]; then
    STRICT_FLAG="--fail-on-empty"
    export HONGZHI_GUARD_REQUIRE_VCS=1
    echo "[hongzhi] strict mode enabled (HONGZHI_VALIDATE_STRICT=1, HONGZHI_GUARD_REQUIRE_VCS=1)"
  fi

  # Skill template audit (post-validate)
  AUDIT_SCRIPT="${SCRIPT_DIR}/skill_template_audit.py"
  if [ -f "$AUDIT_SCRIPT" ]; then
    set +e
    "$PYTHON_BIN" "$AUDIT_SCRIPT" --repo-root "$effective_repo_root" $STRICT_FLAG
    audit_rc=$?
    set -e
    if [ "$audit_rc" -ne 0 ]; then
      echo "[hongzhi][WARN] skill_template_audit FAIL (exit=$audit_rc)" >&2
      runner_rc="$audit_rc"
    fi
  fi

  # Pipeline contract lint (post-validate)
  LINT_SCRIPT="${SCRIPT_DIR}/pipeline_contract_lint.py"
  if [ -f "$LINT_SCRIPT" ]; then
    set +e
    "$PYTHON_BIN" "$LINT_SCRIPT" --repo-root "$effective_repo_root" $STRICT_FLAG
    lint_rc=$?
    set -e
    if [ "$lint_rc" -ne 0 ]; then
      echo "[hongzhi][WARN] pipeline_contract_lint FAIL (exit=$lint_rc)" >&2
      runner_rc="$lint_rc"
    fi
  fi

  GOVERNANCE_CONSISTENCY_SCRIPT="${SCRIPT_DIR}/governance_consistency_guard.py"
  if [ -f "$GOVERNANCE_CONSISTENCY_SCRIPT" ]; then
    set +e
    "$PYTHON_BIN" "$GOVERNANCE_CONSISTENCY_SCRIPT" \
      --repo-root "$effective_repo_root" \
      --require-met-status "${HONGZHI_GOVERNANCE_REQUIRE_MET_STATUS:-1}" \
      --fact-tail-window "${HONGZHI_GOVERNANCE_FACT_TAIL_WINDOW:-17}"
    governance_consistency_rc=$?
    set -e
    if [ "$governance_consistency_rc" -ne 0 ]; then
      echo "[hongzhi][WARN] governance_consistency_guard FAIL (exit=$governance_consistency_rc)" >&2
      runner_rc="$governance_consistency_rc"
    fi
  fi

  TOOL_SYNTAX_SCRIPT="${SCRIPT_DIR}/tool_syntax_guard.py"
  if [ -f "$TOOL_SYNTAX_SCRIPT" ]; then
    set +e
    "$PYTHON_BIN" "$TOOL_SYNTAX_SCRIPT" \
      --repo-root "$effective_repo_root" \
      --strict-source-set "${HONGZHI_TOOL_SYNTAX_STRICT_SET:-1}"
    tool_syntax_rc=$?
    set -e
    if [ "$tool_syntax_rc" -ne 0 ]; then
      echo "[hongzhi][WARN] tool_syntax_guard FAIL (exit=$tool_syntax_rc)" >&2
      runner_rc="$tool_syntax_rc"
    fi
  fi

  PIPELINE_TRUST_COVERAGE_SCRIPT="${SCRIPT_DIR}/pipeline_trust_coverage_guard.py"
  if [ -f "$PIPELINE_TRUST_COVERAGE_SCRIPT" ]; then
    validate_sign_key_env_name="${HONGZHI_BASELINE_SIGN_KEY_ENV:-HONGZHI_BASELINE_SIGN_KEY}"
    if ! [[ "$validate_sign_key_env_name" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
      validate_sign_key_env_name="HONGZHI_BASELINE_SIGN_KEY"
    fi
    set +e
    "$PYTHON_BIN" "$PIPELINE_TRUST_COVERAGE_SCRIPT" \
      --repo-root "$effective_repo_root" \
      --whitelist "${HONGZHI_PIPELINE_TRUST_WHITELIST:-prompt-dsl-system/tools/pipeline_trust_whitelist.json}" \
      --strict-source-set "${HONGZHI_PIPELINE_TRUST_COVERAGE_STRICT_SET:-1}" \
      --require-active "${HONGZHI_PIPELINE_TRUST_COVERAGE_REQUIRE_ACTIVE:-1}" \
      --sign-key-env "$validate_sign_key_env_name" \
      --require-hmac "${HONGZHI_BASELINE_REQUIRE_HMAC:-auto}"
    trust_coverage_rc=$?
    set -e
    if [ "$trust_coverage_rc" -ne 0 ]; then
      echo "[hongzhi][WARN] pipeline_trust_coverage_guard FAIL (exit=$trust_coverage_rc)" >&2
      runner_rc="$trust_coverage_rc"
    fi
  fi

  BASELINE_PROVENANCE_SCRIPT="${SCRIPT_DIR}/baseline_provenance_guard.py"
  if [ -f "$BASELINE_PROVENANCE_SCRIPT" ]; then
    validate_sign_key_env_name="${HONGZHI_BASELINE_SIGN_KEY_ENV:-HONGZHI_BASELINE_SIGN_KEY}"
    if ! [[ "$validate_sign_key_env_name" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
      validate_sign_key_env_name="HONGZHI_BASELINE_SIGN_KEY"
    fi
    set +e
    "$PYTHON_BIN" "$BASELINE_PROVENANCE_SCRIPT" verify \
      --repo-root "$effective_repo_root" \
      --provenance "${HONGZHI_BASELINE_PROVENANCE_FILE:-prompt-dsl-system/tools/baseline_provenance.json}" \
      --strict-source-set "${HONGZHI_BASELINE_PROVENANCE_STRICT_SET:-1}" \
      --max-age-seconds "${HONGZHI_BASELINE_PROVENANCE_MAX_AGE_SECONDS:-0}" \
      --require-git-head "${HONGZHI_BASELINE_PROVENANCE_REQUIRE_GIT:-0}" \
      --sign-key-env "$validate_sign_key_env_name" \
      --require-hmac "${HONGZHI_BASELINE_REQUIRE_HMAC:-auto}"
    provenance_rc=$?
    set -e
    if [ "$provenance_rc" -ne 0 ]; then
      echo "[hongzhi][WARN] baseline_provenance_guard FAIL (exit=$provenance_rc)" >&2
      runner_rc="$provenance_rc"
    fi
  fi

  MUTATION_GUARD_SCRIPT="${SCRIPT_DIR}/gate_mutation_guard.py"
  mutation_enforce_raw="${HONGZHI_MUTATION_GUARD_ENFORCE:-1}"
  mutation_enforce="$(parse_bool "$mutation_enforce_raw" || true)"
  if [ -z "$mutation_enforce" ]; then
    mutation_rc=2
    echo "[hongzhi][WARN] invalid HONGZHI_MUTATION_GUARD_ENFORCE=$mutation_enforce_raw" >&2
    runner_rc=2
  elif [ "$mutation_enforce" -eq 1 ] && [ -f "$MUTATION_GUARD_SCRIPT" ]; then
    set +e
    "$PYTHON_BIN" "$MUTATION_GUARD_SCRIPT" --repo-root "$effective_repo_root"
    mutation_rc=$?
    set -e
    if [ "$mutation_rc" -ne 0 ]; then
      echo "[hongzhi][WARN] gate_mutation_guard FAIL (exit=$mutation_rc)" >&2
      runner_rc="$mutation_rc"
    fi
  fi

  PERFORMANCE_GUARD_SCRIPT="${SCRIPT_DIR}/performance_budget_guard.py"
  performance_enforce_raw="${HONGZHI_PERFORMANCE_GUARD_ENFORCE:-1}"
  performance_enforce="$(parse_bool "$performance_enforce_raw" || true)"
  if [ -z "$performance_enforce" ]; then
    performance_rc=2
    echo "[hongzhi][WARN] invalid HONGZHI_PERFORMANCE_GUARD_ENFORCE=$performance_enforce_raw" >&2
    runner_rc=2
  elif [ "$performance_enforce" -eq 1 ] && [ -f "$PERFORMANCE_GUARD_SCRIPT" ]; then
    perf_trend_enforce="${HONGZHI_PERF_TREND_ENFORCE:-0}"
    perf_history_file="${HONGZHI_PERF_TREND_HISTORY_FILE:-prompt-dsl-system/tools/performance_history.jsonl}"
    perf_history_window="${HONGZHI_PERF_TREND_WINDOW:-30}"
    perf_trend_min_samples="${HONGZHI_PERF_TREND_MIN_SAMPLES:-5}"
    perf_trend_max_ratio="${HONGZHI_PERF_TREND_MAX_RATIO:-1.8}"
    perf_history_write="${HONGZHI_PERF_HISTORY_WRITE:-1}"
    set +e
    "$PYTHON_BIN" "$PERFORMANCE_GUARD_SCRIPT" \
      --repo-root "$effective_repo_root" \
      --max-selfcheck-seconds "${HONGZHI_PERF_MAX_SELFCHECK_SECONDS:-15}" \
      --max-governance-seconds "${HONGZHI_PERF_MAX_GOVERNANCE_SECONDS:-10}" \
      --max-syntax-seconds "${HONGZHI_PERF_MAX_SYNTAX_SECONDS:-25}" \
      --max-trust-coverage-seconds "${HONGZHI_PERF_MAX_TRUST_COVERAGE_SECONDS:-10}" \
      --max-total-seconds "${HONGZHI_PERF_MAX_TOTAL_SECONDS:-70}" \
      --trend-enforce "$perf_trend_enforce" \
      --history-file "$perf_history_file" \
      --history-window "$perf_history_window" \
      --trend-min-samples "$perf_trend_min_samples" \
      --trend-max-ratio "$perf_trend_max_ratio" \
      --history-write "$perf_history_write"
    performance_rc=$?
    set -e
    if [ "$performance_rc" -ne 0 ]; then
      echo "[hongzhi][WARN] performance_budget_guard FAIL (exit=$performance_rc)" >&2
      runner_rc="$performance_rc"
    fi
  fi

  # Contract sample replay (post-validate default gate)
  CONTRACT_REPLAY_SCRIPT="${SCRIPT_DIR}/contract_samples/replay_contract_samples.sh"
  if [ -f "$CONTRACT_REPLAY_SCRIPT" ]; then
    set +e
    bash "$CONTRACT_REPLAY_SCRIPT" --repo-root "$effective_repo_root"
    replay_rc=$?
    set -e
    if [ "$replay_rc" -ne 0 ]; then
      echo "[hongzhi][WARN] contract_sample_replay FAIL (exit=$replay_rc)" >&2
      runner_rc="$replay_rc"
    fi
  else
    echo "[hongzhi][WARN] contract_sample_replay missing: $CONTRACT_REPLAY_SCRIPT" >&2
    replay_rc=2
    runner_rc=2
  fi

  # Kit self-upgrade closure template integrity (post-validate default gate)
  TEMPLATE_GUARD_SCRIPT="${SCRIPT_DIR}/kit_self_upgrade_template_guard.py"
  if [ -f "$TEMPLATE_GUARD_SCRIPT" ]; then
    set +e
    "$PYTHON_BIN" "$TEMPLATE_GUARD_SCRIPT" --repo-root "$effective_repo_root"
    template_guard_rc=$?
    set -e
    if [ "$template_guard_rc" -ne 0 ]; then
      echo "[hongzhi][WARN] template_guard FAIL (exit=$template_guard_rc)" >&2
      runner_rc="$template_guard_rc"
    fi
  else
    echo "[hongzhi][WARN] template_guard missing: $TEMPLATE_GUARD_SCRIPT" >&2
    template_guard_rc=2
    runner_rc=2
  fi

  if [ "$health_report_disabled" -eq 0 ]; then
    POST_VALIDATE_SYNC_SCRIPT="${SCRIPT_DIR}/health_post_validate_sync.py"
    if [ -f "$POST_VALIDATE_SYNC_SCRIPT" ]; then
      audit_status="SKIP"
      lint_status="SKIP"
      replay_status="SKIP"
      template_status="SKIP"
      governance_consistency_status="SKIP"
      tool_syntax_status="SKIP"
      trust_coverage_status="SKIP"
      provenance_status="SKIP"
      mutation_status="SKIP"
      performance_status="SKIP"
      [ "$audit_rc" -gt 0 ] && audit_status="FAIL"
      [ "$lint_rc" -gt 0 ] && lint_status="FAIL"
      [ "$replay_rc" -gt 0 ] && replay_status="FAIL"
      [ "$template_guard_rc" -gt 0 ] && template_status="FAIL"
      [ "$governance_consistency_rc" -gt 0 ] && governance_consistency_status="FAIL"
      [ "$tool_syntax_rc" -gt 0 ] && tool_syntax_status="FAIL"
      [ "$trust_coverage_rc" -gt 0 ] && trust_coverage_status="FAIL"
      [ "$provenance_rc" -gt 0 ] && provenance_status="FAIL"
      [ "$mutation_rc" -gt 0 ] && mutation_status="FAIL"
      [ "$performance_rc" -gt 0 ] && performance_status="FAIL"
      [ "$audit_rc" -eq 0 ] && audit_status="PASS"
      [ "$lint_rc" -eq 0 ] && lint_status="PASS"
      [ "$replay_rc" -eq 0 ] && replay_status="PASS"
      [ "$template_guard_rc" -eq 0 ] && template_status="PASS"
      [ "$governance_consistency_rc" -eq 0 ] && governance_consistency_status="PASS"
      [ "$tool_syntax_rc" -eq 0 ] && tool_syntax_status="PASS"
      [ "$trust_coverage_rc" -eq 0 ] && trust_coverage_status="PASS"
      [ "$provenance_rc" -eq 0 ] && provenance_status="PASS"
      [ "$mutation_rc" -eq 0 ] && mutation_status="PASS"
      [ "$performance_rc" -eq 0 ] && performance_status="PASS"

      output_token_abs="$(resolve_output_token_json_path "$effective_repo_root" "${invoke_args[@]-}")"
      output_dir_abs="$(dirname "$output_token_abs")"
      health_json_path="$(normalize_path_allow_missing "$output_dir_abs/health_report.json")"
      health_md_path="$(normalize_path_allow_missing "$output_dir_abs/health_report.md")"

      set +e
      "$PYTHON_BIN" "$POST_VALIDATE_SYNC_SCRIPT" \
        --repo-root "$effective_repo_root" \
        --report-json "$health_json_path" \
        --report-md "$health_md_path" \
        --gate "skill_template_audit:${audit_status}:${audit_rc}" \
        --gate "pipeline_contract_lint:${lint_status}:${lint_rc}" \
        --gate "governance_consistency_guard:${governance_consistency_status}:${governance_consistency_rc}" \
        --gate "tool_syntax_guard:${tool_syntax_status}:${tool_syntax_rc}" \
        --gate "pipeline_trust_coverage_guard:${trust_coverage_status}:${trust_coverage_rc}" \
        --gate "baseline_provenance_guard:${provenance_status}:${provenance_rc}" \
        --gate "gate_mutation_guard:${mutation_status}:${mutation_rc}" \
        --gate "performance_budget_guard:${performance_status}:${performance_rc}" \
        --gate "contract_sample_replay:${replay_status}:${replay_rc}" \
        --gate "kit_template_guard:${template_status}:${template_guard_rc}"
      sync_rc=$?
      set -e
      if [ "$sync_rc" -ne 0 ]; then
        echo "[hongzhi][WARN] health_post_validate_sync FAIL (exit=$sync_rc)" >&2
        runner_rc="$sync_rc"
      fi
    else
      echo "[hongzhi][WARN] health_post_validate_sync missing: $POST_VALIDATE_SYNC_SCRIPT" >&2
      runner_rc=2
    fi
  fi
fi

if [ "$runner_rc" -eq 4 ]; then
  hint_token_file="$ack_file_abs"
  if [ -z "$hint_token_file" ]; then
    hint_token_file="$effective_repo_root/$TOKEN_JSON_REL_DEFAULT"
    hint_token_file="$(normalize_path_allow_missing "$hint_token_file")"
  fi
  risk_gate_report_file="$(resolve_risk_gate_report_path "$effective_repo_root" "${invoke_args[@]-}")"

  rerun_args=()
  skip_ack_next=0
  for (( i=0; i<${#invoke_args[@]}; i++ )); do
    arg="${invoke_args[$i]}"
    if [ "$skip_ack_next" -eq 1 ]; then
      skip_ack_next=0
      continue
    fi
    case "$arg" in
      --ack)
        skip_ack_next=1
        ;;
      --ack=*)
        ;;
      *)
        rerun_args+=("$arg")
        ;;
    esac
  done

  if [ "$no_ack_hint" -eq 0 ] && [ -f "$TOKEN_RECENCY_PATH" ]; then
    set +e
    "$PYTHON_BIN" "$TOKEN_RECENCY_PATH" --token-file "$hint_token_file" --seconds "$ack_hint_window" >/dev/null 2>&1
    token_fresh_rc=$?
    set -e
    if [ "$token_fresh_rc" -eq 0 ]; then
      hint_cmd="$(build_hint_command "$subcommand" "${rerun_args[@]-}")"
      token_rel="$(to_repo_relative "$effective_repo_root" "$hint_token_file")"
      echo "[hongzhi][RISK-GATE] Token issued. To continue, re-run with:" >&2
      echo "$hint_cmd" >&2
      echo "[hongzhi][RISK-GATE] or use --ack-file $token_rel" >&2
    fi
  fi

  if [ "$auto_ack_latest" -eq 1 ]; then
    policy_allow=0
    policy_deny_reason=""
    policy_blockers=""
    policy_move_available=0
    policy_move_high_risk=""

    if [ -f "$risk_gate_report_file" ]; then
      set +e
      policy_lines="$(read_auto_ack_policy_from_report "$risk_gate_report_file")"
      policy_rc=$?
      set -e
      if [ "$policy_rc" -eq 0 ]; then
        while IFS= read -r line; do
          case "$line" in
            ALLOW=*)
              policy_allow="${line#ALLOW=}"
              ;;
            DENY=*)
              policy_deny_reason="${line#DENY=}"
              ;;
            MOVE_AVAILABLE=*)
              policy_move_available="${line#MOVE_AVAILABLE=}"
              ;;
            MOVE_HIGH_RISK=*)
              policy_move_high_risk="${line#MOVE_HIGH_RISK=}"
              ;;
            BLOCKERS=*)
              policy_blockers="${line#BLOCKERS=}"
              ;;
          esac
        done <<< "$policy_lines"
      else
        policy_allow=0
        policy_deny_reason="failed to parse risk_gate_report.json"
      fi
    else
      policy_allow=0
      policy_deny_reason="risk_gate_report.json not found"
    fi

    if [ "$policy_allow" -ne 1 ]; then
      echo "[hongzhi][RISK-GATE][WARN] auto-ack denied: ${policy_deny_reason:-policy denied}" >&2
      if [ -n "$policy_blockers" ]; then
        echo "[hongzhi][RISK-GATE][WARN] blockers: $policy_blockers" >&2
      fi
      if [[ "$policy_blockers" == *"dst exists"* ]] || [[ "$policy_blockers" == *"destination exists"* ]]; then
        echo "[hongzhi][RISK-GATE][WARN] resolve destination conflicts in move_plan.md before manual ACK." >&2
      fi
      if [[ "$policy_blockers" == *"module_path"* ]] || [[ "$policy_deny_reason" == *"module_path"* ]]; then
        echo "[hongzhi][RISK-GATE][WARN] provide -m/--module-path and regenerate plans." >&2
      fi
      if [ "$policy_move_available" -eq 1 ] && [ -n "$policy_move_high_risk" ] && [ "$policy_move_high_risk" != "0" ]; then
        echo "[hongzhi][RISK-GATE][WARN] move plan high-risk count=$policy_move_high_risk (manual review required)." >&2
      fi
      exit 4
    fi

    if [ ! -f "$hint_token_file" ]; then
      echo "[hongzhi][RISK-GATE][WARN] auto-ack requested but token file not found: $hint_token_file" >&2
      exit 4
    fi

    set +e
    retry_token="$(read_ack_token_from_json "$hint_token_file")"
    retry_token_rc=$?
    set -e
    if [ "$retry_token_rc" -ne 0 ] || [ -z "$retry_token" ]; then
      echo "[hongzhi][RISK-GATE][WARN] auto-ack requested but token unreadable: $hint_token_file" >&2
      exit 4
    fi

    retry_args=("${rerun_args[@]-}" "--ack" "$retry_token")
    set +e
    run_runner_once "$subcommand" "${retry_args[@]-}"
    retry_rc=$?
    set -e
    exit "$retry_rc"
  fi
fi

exit "$runner_rc"
