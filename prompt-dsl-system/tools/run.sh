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
  echo "Usage: $0 <list|validate|run|debug-guard|apply-move|resolve-move-conflicts|scan-followup|apply-followup-fixes|verify-followup-fixes|snapshot-restore-guide|snapshot-prune|snapshot-index|snapshot-open|trace-index|trace-open|trace-diff|trace-bisect|rollback|selfcheck|self-upgrade> [args...]" >&2
  exit 2
fi

subcommand="$1"
requested_subcommand="$subcommand"
shift

case "$subcommand" in
  list|validate|run|debug-guard|apply-move|resolve-move-conflicts|scan-followup|apply-followup-fixes|verify-followup-fixes|snapshot-restore-guide|snapshot-prune|snapshot-index|snapshot-open|trace-index|trace-open|trace-diff|trace-bisect|rollback|selfcheck|self-upgrade) ;;
  *)
    echo "[ERROR] Unsupported subcommand: $subcommand" >&2
    echo "Usage: $0 <list|validate|run|debug-guard|apply-move|resolve-move-conflicts|scan-followup|apply-followup-fixes|verify-followup-fixes|snapshot-restore-guide|snapshot-prune|snapshot-index|snapshot-open|trace-index|trace-open|trace-diff|trace-bisect|rollback|selfcheck|self-upgrade> [args...]" >&2
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

if [ "$requested_subcommand" = "self-upgrade" ] && [ "$strict_self_upgrade" -eq 1 ]; then
  echo "[hongzhi][self-upgrade][strict] preflight start (selfcheck(contract) -> selfcheck_gate -> lint -> audit -> validate)"

  SELFCHECK_SCRIPT="${SCRIPT_DIR}/kit_selfcheck.py"
  SELFCHECK_GATE_SCRIPT="${SCRIPT_DIR}/kit_selfcheck_gate.py"
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
  cleanup_strict_temp() {
    rm -f "$strict_tmp_json" "$strict_tmp_md" "$strict_tmp_gate_json" >/dev/null 2>&1 || true
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
  set +e
  run_runner_once "validate" --repo-root "$effective_repo_root"
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
      [ "$audit_rc" -gt 0 ] && audit_status="FAIL"
      [ "$lint_rc" -gt 0 ] && lint_status="FAIL"
      [ "$replay_rc" -gt 0 ] && replay_status="FAIL"
      [ "$template_guard_rc" -gt 0 ] && template_status="FAIL"
      [ "$audit_rc" -eq 0 ] && audit_status="PASS"
      [ "$lint_rc" -eq 0 ] && lint_status="PASS"
      [ "$replay_rc" -eq 0 ] && replay_status="PASS"
      [ "$template_guard_rc" -eq 0 ] && template_status="PASS"

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
