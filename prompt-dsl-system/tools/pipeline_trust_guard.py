#!/usr/bin/env python3
"""Build/verify trusted pipeline whitelist with content hashes."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

EXIT_INVALID_INPUT = 2
EXIT_TRUST_FAIL = 31
WHITELIST_VERSION = "1.1.0"
DEFAULT_PIPELINE_GLOB = "prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_*.md"
SIGN_KEY_ENV_DEFAULT = "HONGZHI_BASELINE_SIGN_KEY"
REQUIRE_HMAC_ENV = "HONGZHI_BASELINE_REQUIRE_HMAC"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def resolve_sign_key(sign_key_env: str) -> str:
    env_name = str(sign_key_env or "").strip()
    if not env_name:
        return ""
    return str(os.environ.get(env_name, ""))


def resolve_require_hmac(raw: str) -> bool:
    text = str(raw or "").strip()
    if text:
        return parse_bool(text, default=False)
    return parse_bool(os.environ.get(REQUIRE_HMAC_ENV), default=False)


def to_rel(repo_root: Path, path: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def payload_without_signature(document: Dict[str, Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    for key in sorted(document.keys()):
        if key == "signature":
            continue
        payload[key] = document[key]
    return payload


def build_signature(payload: Dict[str, Any], sign_key: str) -> Dict[str, Any]:
    canonical = canonical_json(payload)
    canonical_bytes = canonical.encode("utf-8")
    content_sha = sha256_bytes(canonical_bytes)
    signature: Dict[str, Any] = {
        "scheme": "sha256",
        "content_sha256": content_sha,
        "signed_at": now_iso(),
    }
    if sign_key:
        key_bytes = sign_key.encode("utf-8")
        signature["scheme"] = "hmac-sha256"
        signature["hmac_sha256"] = hmac.new(key_bytes, canonical_bytes, hashlib.sha256).hexdigest()
        signature["key_id"] = sha256_bytes(key_bytes)[:12]
    return signature


def verify_signature(
    document: Dict[str, Any],
    sign_key: str,
    require_hmac: bool,
) -> Tuple[List[str], Dict[str, Any]]:
    violations: List[str] = []
    payload = payload_without_signature(document)
    canonical = canonical_json(payload)
    canonical_bytes = canonical.encode("utf-8")
    computed_content_sha = sha256_bytes(canonical_bytes)

    signature_raw = document.get("signature")
    if not isinstance(signature_raw, dict):
        violations.append("signature missing or invalid")
        return violations, {
            "scheme": "",
            "sign_key_present": bool(sign_key),
            "require_hmac": bool(require_hmac),
            "computed_content_sha256": computed_content_sha,
            "signature_valid": False,
        }

    scheme = str(signature_raw.get("scheme", "")).strip().lower()
    content_sha = str(signature_raw.get("content_sha256", "")).strip()
    if not content_sha:
        violations.append("signature.content_sha256 missing")
    elif content_sha != computed_content_sha:
        violations.append(
            f"signature content_sha256 mismatch: expected={computed_content_sha} actual={content_sha}"
        )

    if scheme == "hmac-sha256":
        expected_hmac = str(signature_raw.get("hmac_sha256", "")).strip()
        if not expected_hmac:
            violations.append("signature.hmac_sha256 missing")
        if not sign_key:
            violations.append("hmac sign key missing from environment")
        else:
            actual_hmac = hmac.new(
                sign_key.encode("utf-8"),
                canonical_bytes,
                hashlib.sha256,
            ).hexdigest()
            if expected_hmac and expected_hmac != actual_hmac:
                violations.append(
                    f"signature hmac mismatch: expected={actual_hmac} actual={expected_hmac}"
                )
    elif scheme == "sha256":
        if require_hmac:
            violations.append("signature scheme sha256 is not allowed when require_hmac=true")
    else:
        violations.append(f"signature.scheme invalid: {scheme or '<empty>'}")

    return violations, {
        "scheme": scheme,
        "sign_key_present": bool(sign_key),
        "require_hmac": bool(require_hmac),
        "computed_content_sha256": computed_content_sha,
        "signature_valid": len(violations) == 0,
    }


def list_pipelines(repo_root: Path, pipeline_glob: str) -> Dict[str, Path]:
    files: Dict[str, Path] = {}
    for fp in sorted(repo_root.glob(pipeline_glob)):
        if not fp.is_file():
            continue
        rel = to_rel(repo_root, fp)
        files[rel] = fp.resolve()
    return files


def normalize_pipeline_arg(repo_root: Path, pipeline_arg: str) -> Tuple[Path | None, str | None]:
    candidate = Path(pipeline_arg).expanduser()
    if not candidate.is_absolute():
        candidate = (repo_root / candidate).resolve()
    else:
        candidate = candidate.resolve()
    try:
        rel = candidate.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return None, None
    return candidate, rel


def build_whitelist(repo_root: Path, pipeline_glob: str, sign_key: str) -> Dict[str, Any]:
    pipelines = list_pipelines(repo_root, pipeline_glob)
    entries: List[Dict[str, Any]] = []
    for rel in sorted(pipelines.keys()):
        fp = pipelines[rel]
        entries.append(
            {
                "path": rel,
                "sha256": sha256_file(fp),
                "status": "active",
            }
        )

    whitelist: Dict[str, Any] = {
        "tool": "pipeline_trust_guard",
        "whitelist_version": WHITELIST_VERSION,
        "generated_at": now_iso(),
        "repo_root": ".",
        "pipeline_glob": pipeline_glob,
        "entries": entries,
        "summary": {
            "pipeline_count": len(entries),
        },
    }
    whitelist["signature"] = build_signature(payload_without_signature(whitelist), sign_key)
    return whitelist


def load_whitelist(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def parse_entries(entries_raw: Any) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    entries: Dict[str, Dict[str, Any]] = {}
    violations: List[str] = []
    if not isinstance(entries_raw, list):
        return entries, ["whitelist entries missing or invalid"]
    for item in entries_raw:
        if not isinstance(item, dict):
            violations.append("whitelist entry is not an object")
            continue
        rel = str(item.get("path", "")).strip().replace("\\", "/")
        if not rel:
            violations.append("whitelist entry path missing")
            continue
        if rel in entries:
            violations.append(f"duplicate whitelist path: {rel}")
            continue
        entries[rel] = item
    if not entries:
        violations.append("whitelist entries empty")
    return entries, violations


def verify_pipeline(
    repo_root: Path,
    pipeline_arg: str,
    whitelist: Dict[str, Any],
    strict_source_set: bool,
    require_active: bool,
    sign_key: str,
    require_hmac: bool,
) -> Dict[str, Any]:
    violations: List[str] = []
    sig_violations, sig_actual = verify_signature(whitelist, sign_key=sign_key, require_hmac=require_hmac)
    violations.extend(sig_violations)

    pipeline_path, pipeline_rel = normalize_pipeline_arg(repo_root, pipeline_arg)
    if pipeline_path is None or pipeline_rel is None:
        violations.append(f"pipeline path outside repo-root: {pipeline_arg}")
        return {
            "passed": False,
            "violations": violations,
            "actual": {},
            "signature": sig_actual,
            "threshold": {
                "strict_source_set": strict_source_set,
                "require_active": require_active,
            },
        }
    if not pipeline_path.is_file():
        violations.append(f"pipeline file not found: {pipeline_path}")
        return {
            "passed": False,
            "violations": violations,
            "actual": {
                "pipeline": pipeline_rel,
            },
            "signature": sig_actual,
            "threshold": {
                "strict_source_set": strict_source_set,
                "require_active": require_active,
            },
        }

    entries, entry_violations = parse_entries(whitelist.get("entries"))
    violations.extend(entry_violations)

    pipeline_glob = str(whitelist.get("pipeline_glob", DEFAULT_PIPELINE_GLOB)).strip()
    if not pipeline_glob:
        pipeline_glob = DEFAULT_PIPELINE_GLOB

    entry = entries.get(pipeline_rel)
    if not entry:
        violations.append(f"pipeline not in whitelist: {pipeline_rel}")
        entry = {}

    status = str(entry.get("status", "active")).strip().lower() if entry else ""
    expected_sha = str(entry.get("sha256", "")).strip() if entry else ""
    actual_sha = sha256_file(pipeline_path)

    if require_active and entry and status != "active":
        violations.append(f"pipeline status is not active: {pipeline_rel} status={status}")
    if entry and not expected_sha:
        violations.append(f"whitelist sha256 missing: {pipeline_rel}")
    if entry and expected_sha and actual_sha != expected_sha:
        violations.append(
            f"sha256 mismatch: {pipeline_rel} expected={expected_sha} actual={actual_sha}"
        )

    current_pipelines = list_pipelines(repo_root, pipeline_glob)
    current_set = set(current_pipelines.keys())
    whitelist_set = set(entries.keys())
    missing_files = sorted(whitelist_set - current_set)
    unexpected_files = sorted(current_set - whitelist_set)
    if strict_source_set:
        for rel in missing_files:
            violations.append(f"source-set missing pipeline: {rel}")
        for rel in unexpected_files:
            violations.append(f"source-set drift unexpected pipeline: {rel}")

    return {
        "passed": len(violations) == 0,
        "threshold": {
            "strict_source_set": strict_source_set,
            "require_active": require_active,
            "pipeline_glob": pipeline_glob,
        },
        "signature": sig_actual,
        "actual": {
            "pipeline": pipeline_rel,
            "status": status if entry else "",
            "expected_sha256": expected_sha if entry else "",
            "actual_sha256": actual_sha,
            "whitelist_pipeline_count": len(whitelist_set),
            "current_pipeline_count": len(current_set),
            "missing_pipelines": missing_files,
            "unexpected_pipelines": unexpected_files,
        },
        "violations": violations,
    }


def cmd_build(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).expanduser().resolve()
    whitelist_path = Path(args.whitelist).expanduser().resolve()
    pipeline_glob = str(args.pipeline_glob).strip() or DEFAULT_PIPELINE_GLOB
    sign_key = resolve_sign_key(args.sign_key_env)
    if not repo_root.is_dir():
        print(f"[pipeline_trust] FAIL: invalid repo-root: {repo_root}")
        return EXIT_INVALID_INPUT
    whitelist = build_whitelist(repo_root, pipeline_glob, sign_key=sign_key)
    whitelist_path.parent.mkdir(parents=True, exist_ok=True)
    whitelist_path.write_text(
        json.dumps(whitelist, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    sig = whitelist.get("signature") if isinstance(whitelist.get("signature"), dict) else {}
    print(
        f"[pipeline_trust] BUILD: whitelist={whitelist_path} pipelines={whitelist['summary']['pipeline_count']} signature_scheme={sig.get('scheme', '-') }"
    )
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).expanduser().resolve()
    whitelist_path = Path(args.whitelist).expanduser().resolve()
    strict_source_set = parse_bool(args.strict_source_set, default=True)
    require_active = parse_bool(args.require_active, default=True)
    require_hmac = resolve_require_hmac(args.require_hmac)
    sign_key = resolve_sign_key(args.sign_key_env)
    if not repo_root.is_dir():
        print(f"[pipeline_trust] FAIL: invalid repo-root: {repo_root}")
        return EXIT_INVALID_INPUT
    if not whitelist_path.is_file():
        print(f"[pipeline_trust] FAIL: whitelist not found: {whitelist_path}")
        return EXIT_INVALID_INPUT
    whitelist = load_whitelist(whitelist_path)
    if not whitelist:
        print(f"[pipeline_trust] FAIL: invalid whitelist JSON: {whitelist_path}")
        return EXIT_INVALID_INPUT

    result = verify_pipeline(
        repo_root=repo_root,
        pipeline_arg=str(args.pipeline),
        whitelist=whitelist,
        strict_source_set=strict_source_set,
        require_active=require_active,
        sign_key=sign_key,
        require_hmac=require_hmac,
    )

    out_json_path: Path | None = None
    if args.out_json:
        out_json_path = Path(args.out_json).expanduser().resolve()
        out_json_path.parent.mkdir(parents=True, exist_ok=True)
        out_json_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    if result["passed"]:
        actual = result["actual"]
        signature = result.get("signature", {})
        print(
            "[pipeline_trust] PASS: "
            f"pipeline={actual.get('pipeline')} "
            f"status={actual.get('status', 'active')} "
            f"strict_source_set={strict_source_set} "
            f"signature_scheme={signature.get('scheme', '-')}"
        )
        if out_json_path is not None:
            print(f"[pipeline_trust] report={out_json_path}")
        return 0

    print("[pipeline_trust] FAIL")
    for violation in result["violations"]:
        print(f"[pipeline_trust] violation: {violation}")
    if out_json_path is not None:
        print(f"[pipeline_trust] report={out_json_path}")
    return EXIT_TRUST_FAIL


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build/verify trusted pipeline whitelist with content hashes"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build_p = sub.add_parser("build", help="Build whitelist from pipeline markdown files")
    build_p.add_argument("--repo-root", default=".", help="Repository root path")
    build_p.add_argument(
        "--whitelist",
        default="prompt-dsl-system/tools/pipeline_trust_whitelist.json",
        help="Output whitelist path",
    )
    build_p.add_argument(
        "--pipeline-glob",
        default=DEFAULT_PIPELINE_GLOB,
        help="Glob expression to include trusted pipelines",
    )
    build_p.add_argument(
        "--sign-key-env",
        default=SIGN_KEY_ENV_DEFAULT,
        help="Environment variable name for optional HMAC sign key",
    )
    build_p.set_defaults(func=cmd_build)

    verify_p = sub.add_parser("verify", help="Verify one pipeline against whitelist")
    verify_p.add_argument("--repo-root", default=".", help="Repository root path")
    verify_p.add_argument("--pipeline", required=True, help="Pipeline path (absolute or repo-relative)")
    verify_p.add_argument(
        "--whitelist",
        default="prompt-dsl-system/tools/pipeline_trust_whitelist.json",
        help="Whitelist path",
    )
    verify_p.add_argument(
        "--strict-source-set",
        default="true",
        help="true/false; when true, fail on pipeline set drift",
    )
    verify_p.add_argument(
        "--require-active",
        default="true",
        help="true/false; when true, pipeline status must be active",
    )
    verify_p.add_argument(
        "--sign-key-env",
        default=SIGN_KEY_ENV_DEFAULT,
        help="Environment variable name for optional HMAC sign key",
    )
    verify_p.add_argument(
        "--require-hmac",
        default="",
        help=f"true/false; default from {REQUIRE_HMAC_ENV}",
    )
    verify_p.add_argument("--out-json", default="", help="Optional output path for verify report JSON")
    verify_p.set_defaults(func=cmd_verify)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
