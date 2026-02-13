#!/usr/bin/env python3
"""Build/verify integrity manifest for kit critical assets."""

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
EXIT_VERIFY_FAIL = 29
MANIFEST_VERSION = "1.1.0"
SIGN_KEY_ENV_DEFAULT = "HONGZHI_BASELINE_SIGN_KEY"
REQUIRE_HMAC_ENV = "HONGZHI_BASELINE_REQUIRE_HMAC"

DEFAULT_TRACKED_PATHS = [
    "prompt-dsl-system/tools/run.sh",
    "prompt-dsl-system/tools/intent_router.py",
    "prompt-dsl-system/tools/golden_path_regression.sh",
    "prompt-dsl-system/tools/pipeline_runner.py",
    "prompt-dsl-system/tools/kit_selfcheck.py",
    "prompt-dsl-system/tools/kit_selfcheck_gate.py",
    "prompt-dsl-system/tools/kit_selfcheck_freshness_gate.py",
    "prompt-dsl-system/tools/kit_integrity_guard.py",
    "prompt-dsl-system/tools/pipeline_trust_guard.py",
    "prompt-dsl-system/tools/pipeline_trust_coverage_guard.py",
    "prompt-dsl-system/tools/baseline_provenance_guard.py",
    "prompt-dsl-system/tools/governance_consistency_guard.py",
    "prompt-dsl-system/tools/tool_syntax_guard.py",
    "prompt-dsl-system/tools/gate_mutation_guard.py",
    "prompt-dsl-system/tools/performance_budget_guard.py",
    "prompt-dsl-system/tools/hmac_strict_smoke.py",
    "prompt-dsl-system/tools/fuzz_contract_pipeline_gate.py",
    "prompt-dsl-system/tools/BASELINE_KEY_GOVERNANCE.md",
    "prompt-dsl-system/tools/baseline_provenance.json",
    "prompt-dsl-system/tools/pipeline_trust_whitelist.json",
    "prompt-dsl-system/tools/kit_dual_approval_guard.py",
    "prompt-dsl-system/tools/baseline_dual_approval.template.json",
    "prompt-dsl-system/tools/contract_validator.py",
    "prompt-dsl-system/tools/contract_schema_v1.json",
    "prompt-dsl-system/tools/contract_schema_v2.json",
    "prompt-dsl-system/tools/kit_self_upgrade_template_guard.py",
    ".github/workflows/kit_guardrails.yml",
]

DEFAULT_TRACKED_GLOBS = [
    "prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_*.md",
    "prompt-dsl-system/tools/artifacts/templates/kit_self_upgrade/*.template.md",
    "prompt-dsl-system/tools/contract_samples/*.log",
]


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


def collect_tracked_files(
    repo_root: Path,
    tracked_paths: List[str],
    tracked_globs: List[str],
) -> Tuple[Dict[str, Path], List[str]]:
    files: Dict[str, Path] = {}
    missing_explicit: List[str] = []
    for rel in tracked_paths:
        rel_path = str(rel).strip().replace("\\", "/")
        if not rel_path:
            continue
        candidate = (repo_root / rel_path).resolve()
        if candidate.is_file():
            files[rel_path] = candidate
        else:
            missing_explicit.append(rel_path)

    for pattern in tracked_globs:
        glob_expr = str(pattern).strip()
        if not glob_expr:
            continue
        for matched in sorted(repo_root.glob(glob_expr)):
            if not matched.is_file():
                continue
            rel = to_rel(repo_root, matched)
            files[rel] = matched.resolve()

    return files, missing_explicit


def build_manifest(repo_root: Path, sign_key: str) -> Dict[str, Any]:
    files, missing_explicit = collect_tracked_files(
        repo_root,
        tracked_paths=DEFAULT_TRACKED_PATHS,
        tracked_globs=DEFAULT_TRACKED_GLOBS,
    )
    if missing_explicit:
        raise FileNotFoundError(
            "tracked path missing: " + ", ".join(sorted(missing_explicit))
        )

    entries: List[Dict[str, Any]] = []
    for rel in sorted(files.keys()):
        fp = files[rel]
        entries.append(
            {
                "path": rel,
                "sha256": sha256_file(fp),
                "size": int(fp.stat().st_size),
            }
        )

    manifest: Dict[str, Any] = {
        "tool": "kit_integrity_guard",
        "manifest_version": MANIFEST_VERSION,
        "generated_at": now_iso(),
        "repo_root": ".",
        "tracked": {
            "paths": DEFAULT_TRACKED_PATHS,
            "globs": DEFAULT_TRACKED_GLOBS,
        },
        "entries": entries,
        "summary": {
            "file_count": len(entries),
        },
    }
    manifest["signature"] = build_signature(payload_without_signature(manifest), sign_key)
    return manifest


def load_manifest(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def parse_manifest_entries(entries_raw: Any) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    entries: Dict[str, Dict[str, Any]] = {}
    violations: List[str] = []
    if not isinstance(entries_raw, list):
        return entries, ["manifest entries missing or invalid"]
    for item in entries_raw:
        if not isinstance(item, dict):
            violations.append("manifest entry is not an object")
            continue
        rel = str(item.get("path", "")).strip().replace("\\", "/")
        if not rel:
            violations.append("manifest entry path missing")
            continue
        if rel in entries:
            violations.append(f"duplicate manifest path: {rel}")
            continue
        entries[rel] = item
    if not entries:
        violations.append("manifest entries empty")
    return entries, violations


def verify_manifest(
    repo_root: Path,
    manifest: Dict[str, Any],
    strict_source_set: bool,
    sign_key: str,
    require_hmac: bool,
) -> Dict[str, Any]:
    tracked = manifest.get("tracked") if isinstance(manifest.get("tracked"), dict) else {}
    tracked_paths = tracked.get("paths") if isinstance(tracked.get("paths"), list) else DEFAULT_TRACKED_PATHS
    tracked_globs = tracked.get("globs") if isinstance(tracked.get("globs"), list) else DEFAULT_TRACKED_GLOBS
    tracked_paths = [str(x) for x in tracked_paths]
    tracked_globs = [str(x) for x in tracked_globs]

    violations: List[str] = []
    sig_violations, sig_actual = verify_signature(manifest, sign_key=sign_key, require_hmac=require_hmac)
    violations.extend(sig_violations)

    current_files, missing_explicit = collect_tracked_files(repo_root, tracked_paths, tracked_globs)
    if missing_explicit:
        for rel in sorted(missing_explicit):
            violations.append(f"tracked path missing: {rel}")

    expected_map, entry_violations = parse_manifest_entries(manifest.get("entries"))
    violations.extend(entry_violations)

    expected_paths = set(expected_map.keys())
    current_paths = set(current_files.keys())
    missing_files = sorted(expected_paths - current_paths)
    unexpected_files = sorted(current_paths - expected_paths)

    if strict_source_set:
        for rel in missing_files:
            violations.append(f"source-set missing file: {rel}")
        for rel in unexpected_files:
            violations.append(f"source-set drift unexpected file: {rel}")

    hash_mismatches: List[str] = []
    for rel in sorted(expected_paths & current_paths):
        fp = current_files[rel]
        actual_sha = sha256_file(fp)
        expected_sha = str(expected_map[rel].get("sha256", "")).strip()
        if not expected_sha:
            violations.append(f"manifest sha256 missing: {rel}")
            continue
        if actual_sha != expected_sha:
            hash_mismatches.append(rel)
            violations.append(
                f"sha256 mismatch: {rel} expected={expected_sha} actual={actual_sha}"
            )

    return {
        "passed": len(violations) == 0,
        "strict_source_set": strict_source_set,
        "tracked": {
            "paths": tracked_paths,
            "globs": tracked_globs,
        },
        "signature": sig_actual,
        "actual": {
            "expected_file_count": len(expected_paths),
            "current_file_count": len(current_paths),
            "missing_files": missing_files,
            "unexpected_files": unexpected_files,
            "hash_mismatches": hash_mismatches,
        },
        "violations": violations,
    }


def cmd_build(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).expanduser().resolve()
    manifest_path = Path(args.manifest).expanduser().resolve()
    sign_key = resolve_sign_key(args.sign_key_env)
    if not repo_root.is_dir():
        print(f"[kit_integrity] FAIL: invalid repo-root: {repo_root}")
        return EXIT_INVALID_INPUT
    try:
        manifest = build_manifest(repo_root, sign_key=sign_key)
    except FileNotFoundError as exc:
        print(f"[kit_integrity] FAIL: {exc}")
        return EXIT_INVALID_INPUT
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    sig = manifest.get("signature") if isinstance(manifest.get("signature"), dict) else {}
    print(
        f"[kit_integrity] BUILD: manifest={manifest_path} files={manifest['summary']['file_count']} signature_scheme={sig.get('scheme', '-') }"
    )
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).expanduser().resolve()
    manifest_path = Path(args.manifest).expanduser().resolve()
    strict_source_set = parse_bool(args.strict_source_set, default=True)
    require_hmac = resolve_require_hmac(args.require_hmac)
    sign_key = resolve_sign_key(args.sign_key_env)
    if not repo_root.is_dir():
        print(f"[kit_integrity] FAIL: invalid repo-root: {repo_root}")
        return EXIT_INVALID_INPUT
    if not manifest_path.is_file():
        print(f"[kit_integrity] FAIL: manifest not found: {manifest_path}")
        return EXIT_INVALID_INPUT

    manifest = load_manifest(manifest_path)
    if not manifest:
        print(f"[kit_integrity] FAIL: invalid manifest JSON: {manifest_path}")
        return EXIT_INVALID_INPUT

    result = verify_manifest(
        repo_root=repo_root,
        manifest=manifest,
        strict_source_set=strict_source_set,
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
            "[kit_integrity] PASS: "
            f"expected={actual['expected_file_count']} "
            f"current={actual['current_file_count']} "
            f"strict_source_set={strict_source_set} "
            f"signature_scheme={signature.get('scheme', '-') }"
        )
        if out_json_path is not None:
            print(f"[kit_integrity] report={out_json_path}")
        return 0

    print("[kit_integrity] FAIL")
    for violation in result["violations"]:
        print(f"[kit_integrity] violation: {violation}")
    if out_json_path is not None:
        print(f"[kit_integrity] report={out_json_path}")
    return EXIT_VERIFY_FAIL


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build/verify integrity manifest for kit core assets"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build_p = sub.add_parser("build", help="Build integrity manifest")
    build_p.add_argument("--repo-root", default=".", help="Repository root path")
    build_p.add_argument(
        "--manifest",
        default="prompt-dsl-system/tools/kit_integrity_manifest.json",
        help="Output manifest path",
    )
    build_p.add_argument(
        "--sign-key-env",
        default=SIGN_KEY_ENV_DEFAULT,
        help="Environment variable name for optional HMAC sign key",
    )
    build_p.set_defaults(func=cmd_build)

    verify_p = sub.add_parser("verify", help="Verify integrity manifest")
    verify_p.add_argument("--repo-root", default=".", help="Repository root path")
    verify_p.add_argument(
        "--manifest",
        default="prompt-dsl-system/tools/kit_integrity_manifest.json",
        help="Manifest path",
    )
    verify_p.add_argument(
        "--strict-source-set",
        default="true",
        help="true/false; when true, fail on missing/unexpected tracked files",
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
