#!/usr/bin/env python3
"""Verify whitelist coverage/hash status for all pipeline markdown files."""

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
EXIT_GUARD_FAIL = 38
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


def resolve_require_hmac(raw: str, sign_key_present: bool) -> bool:
    text = str(raw or "").strip()
    if text and text.lower() != "auto":
        return parse_bool(text, default=False)
    if text.lower() == "auto":
        return bool(sign_key_present)
    env_text = str(os.environ.get(REQUIRE_HMAC_ENV, "")).strip()
    if env_text.lower() == "auto":
        return bool(sign_key_present)
    if env_text:
        return parse_bool(env_text, default=False)
    return False


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
    return {key: document[key] for key in sorted(document.keys()) if key != "signature"}


def verify_signature(whitelist: Dict[str, Any], sign_key: str, require_hmac: bool) -> Tuple[List[str], Dict[str, Any]]:
    violations: List[str] = []
    payload = payload_without_signature(whitelist)
    canonical = canonical_json(payload)
    canonical_bytes = canonical.encode("utf-8")
    computed_content_sha = sha256_bytes(canonical_bytes)

    signature_raw = whitelist.get("signature")
    if not isinstance(signature_raw, dict):
        violations.append("signature missing or invalid")
        return violations, {
            "scheme": "",
            "computed_content_sha256": computed_content_sha,
            "sign_key_present": bool(sign_key),
            "require_hmac": bool(require_hmac),
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
            actual_hmac = hmac.new(sign_key.encode("utf-8"), canonical_bytes, hashlib.sha256).hexdigest()
            if expected_hmac and expected_hmac != actual_hmac:
                violations.append(f"signature hmac mismatch: expected={actual_hmac} actual={expected_hmac}")
    elif scheme == "sha256":
        if require_hmac:
            violations.append("signature scheme sha256 is not allowed when require_hmac=true")
    else:
        violations.append(f"signature.scheme invalid: {scheme or '<empty>'}")

    return violations, {
        "scheme": scheme,
        "computed_content_sha256": computed_content_sha,
        "sign_key_present": bool(sign_key),
        "require_hmac": bool(require_hmac),
        "signature_valid": len(violations) == 0,
    }


def to_rel(repo_root: Path, path: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def list_pipelines(repo_root: Path, pipeline_glob: str) -> Dict[str, Path]:
    items: Dict[str, Path] = {}
    for fp in sorted(repo_root.glob(pipeline_glob)):
        if not fp.is_file():
            continue
        rel = to_rel(repo_root, fp)
        items[rel] = fp.resolve()
    return items


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
            violations.append(f"duplicate whitelist entry path: {rel}")
            continue
        entries[rel] = item
    if not entries:
        violations.append("whitelist entries empty")
    return entries, violations


def run_guard(
    repo_root: Path,
    whitelist_path: Path,
    pipeline_glob_override: str,
    strict_source_set: bool,
    require_active: bool,
    sign_key_env: str,
    require_hmac_raw: str,
) -> Dict[str, Any]:
    violations: List[str] = []

    try:
        whitelist = json.loads(whitelist_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "tool": "pipeline_trust_coverage_guard",
            "generated_at": now_iso(),
            "repo_root": str(repo_root),
            "whitelist": str(whitelist_path),
            "violations": [f"failed to read whitelist: {exc}"],
            "summary": {
                "checks_total": 0,
                "checks_passed": 0,
                "checks_failed": 1,
                "passed": False,
            },
        }

    if not isinstance(whitelist, dict):
        whitelist = {}

    sign_key = resolve_sign_key(sign_key_env)
    require_hmac = resolve_require_hmac(require_hmac_raw, sign_key_present=bool(sign_key))
    sig_violations, signature_actual = verify_signature(whitelist, sign_key=sign_key, require_hmac=require_hmac)
    violations.extend(sig_violations)

    entries, entry_violations = parse_entries(whitelist.get("entries"))
    violations.extend(entry_violations)

    pipeline_glob = str(pipeline_glob_override or "").strip()
    if not pipeline_glob:
        pipeline_glob = str(whitelist.get("pipeline_glob", DEFAULT_PIPELINE_GLOB)).strip() or DEFAULT_PIPELINE_GLOB

    pipelines = list_pipelines(repo_root, pipeline_glob)
    if not pipelines:
        violations.append("no pipeline files found for coverage check")

    pipeline_checks: List[Dict[str, Any]] = []
    for rel, path in sorted(pipelines.items()):
        entry = entries.get(rel)
        status = str(entry.get("status", "")).strip().lower() if isinstance(entry, dict) else ""
        expected_sha = str(entry.get("sha256", "")).strip() if isinstance(entry, dict) else ""
        actual_sha = sha256_file(path)

        item_violations: List[str] = []
        if entry is None:
            item_violations.append("missing whitelist entry")
            violations.append(f"missing whitelist entry: {rel}")
        else:
            if not expected_sha:
                item_violations.append("whitelist sha256 missing")
                violations.append(f"whitelist sha256 missing: {rel}")
            elif expected_sha != actual_sha:
                item_violations.append("sha256 mismatch")
                violations.append(f"sha256 mismatch: {rel} expected={expected_sha} actual={actual_sha}")
            if require_active and status != "active":
                item_violations.append(f"status not active: {status or '<empty>'}")
                violations.append(f"pipeline status is not active: {rel} status={status or '<empty>'}")

        pipeline_checks.append(
            {
                "path": rel,
                "status": status,
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha,
                "passed": len(item_violations) == 0,
                "violations": item_violations,
            }
        )

    current_set = set(pipelines.keys())
    whitelist_set = set(entries.keys())
    source_missing = sorted(whitelist_set - current_set)
    source_unexpected = sorted(current_set - whitelist_set)

    if strict_source_set:
        for rel in source_missing:
            violations.append(f"source-set missing pipeline file: {rel}")
        for rel in source_unexpected:
            violations.append(f"source-set unexpected pipeline file: {rel}")

    checks_total = len(pipeline_checks)
    checks_failed = sum(1 for item in pipeline_checks if not item.get("passed", False))
    checks_passed = checks_total - checks_failed
    if checks_passed < 0:
        checks_passed = 0

    report: Dict[str, Any] = {
        "tool": "pipeline_trust_coverage_guard",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "whitelist": str(whitelist_path),
        "inputs": {
            "pipeline_glob": pipeline_glob,
            "strict_source_set": bool(strict_source_set),
            "require_active": bool(require_active),
            "sign_key_env": sign_key_env,
            "require_hmac": bool(require_hmac),
        },
        "actual": {
            "pipeline_count": len(pipeline_checks),
            "entry_count": len(entries),
            "source_set_missing": source_missing,
            "source_set_unexpected": source_unexpected,
            "pipeline_checks": pipeline_checks,
            "signature": signature_actual,
        },
        "violations": violations,
        "summary": {
            "checks_total": checks_total,
            "checks_passed": checks_passed,
            "checks_failed": checks_failed,
            "passed": len(violations) == 0,
        },
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify trust whitelist coverage/hash/status for all pipelines.")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument(
        "--whitelist",
        default="prompt-dsl-system/tools/pipeline_trust_whitelist.json",
        help="Whitelist json path (relative to repo-root by default).",
    )
    parser.add_argument(
        "--pipeline-glob",
        default="",
        help="Optional pipeline glob override (relative to repo-root).",
    )
    parser.add_argument("--strict-source-set", default="true")
    parser.add_argument("--require-active", default="true")
    parser.add_argument("--sign-key-env", default=SIGN_KEY_ENV_DEFAULT)
    parser.add_argument("--require-hmac", default="")
    parser.add_argument("--out-json", default="")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    if not repo_root.is_dir():
        print(f"[pipeline_trust_coverage] FAIL: invalid repo_root: {repo_root}")
        return EXIT_INVALID_INPUT

    whitelist = Path(args.whitelist).expanduser()
    if not whitelist.is_absolute():
        whitelist = (repo_root / whitelist).resolve()
    if not whitelist.is_file():
        print(f"[pipeline_trust_coverage] FAIL: whitelist not found: {whitelist}")
        return EXIT_INVALID_INPUT

    report = run_guard(
        repo_root=repo_root,
        whitelist_path=whitelist,
        pipeline_glob_override=args.pipeline_glob,
        strict_source_set=parse_bool(args.strict_source_set, default=True),
        require_active=parse_bool(args.require_active, default=True),
        sign_key_env=str(args.sign_key_env or SIGN_KEY_ENV_DEFAULT).strip() or SIGN_KEY_ENV_DEFAULT,
        require_hmac_raw=args.require_hmac,
    )

    out_json = str(args.out_json or "").strip()
    if out_json:
        out_path = Path(out_json).expanduser()
        if not out_path.is_absolute():
            out_path = (repo_root / out_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = report.get("summary", {}) if isinstance(report, dict) else {}
    passed = bool(summary.get("passed", False))
    checks_passed = int(summary.get("checks_passed", 0))
    checks_total = int(summary.get("checks_total", 0))
    violations = report.get("violations", []) if isinstance(report, dict) else []

    if passed:
        print(f"[pipeline_trust_coverage] PASS checks={checks_passed}/{checks_total}")
        return 0

    print(f"[pipeline_trust_coverage] FAIL checks={checks_passed}/{checks_total} violations={len(violations)}")
    for item in violations:
        print(f"  - {item}")
    return EXIT_GUARD_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
