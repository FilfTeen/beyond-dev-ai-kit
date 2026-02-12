#!/usr/bin/env python3
"""Build/verify baseline provenance attestation for critical governance assets."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

EXIT_INVALID_INPUT = 2
EXIT_VERIFY_FAIL = 39
PROVENANCE_VERSION = "1.0.0"
SIGN_KEY_ENV_DEFAULT = "HONGZHI_BASELINE_SIGN_KEY"
REQUIRE_HMAC_ENV = "HONGZHI_BASELINE_REQUIRE_HMAC"

DEFAULT_TRACKED_PATHS = [
    "prompt-dsl-system/tools/pipeline_trust_whitelist.json",
    "prompt-dsl-system/00_conventions/HONGZHI_COMPANY_CONSTITUTION.md",
    "prompt-dsl-system/00_conventions/COMPLIANCE_MATRIX.md",
    "prompt-dsl-system/00_conventions/FACT_BASELINE.md",
    ".github/workflows/kit_guardrails.yml",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso_datetime(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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
    text = str(raw or "").strip().lower()
    if text and text != "auto":
        return parse_bool(text, default=False)
    if text == "auto":
        return bool(sign_key_present)
    env_text = str(os.environ.get(REQUIRE_HMAC_ENV, "")).strip().lower()
    if env_text == "auto":
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


def get_repo_snapshot(repo_root: Path) -> Dict[str, Any]:
    git_head = ""
    head_available = False
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--verify", "HEAD"],
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            git_head = str(proc.stdout or "").strip()
            head_available = bool(git_head)
    except OSError:
        pass
    return {
        "git_head": git_head,
        "git_head_available": bool(head_available),
    }


def build_signature(payload: Dict[str, Any], sign_key: str) -> Dict[str, Any]:
    canonical = canonical_json(payload)
    canonical_bytes = canonical.encode("utf-8")
    signature: Dict[str, Any] = {
        "scheme": "sha256",
        "content_sha256": sha256_bytes(canonical_bytes),
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
        "sign_key_present": bool(sign_key),
        "require_hmac": bool(require_hmac),
        "computed_content_sha256": computed_content_sha,
        "signature_valid": len(violations) == 0,
    }


def collect_files(repo_root: Path, tracked_paths: List[str]) -> Tuple[Dict[str, Path], List[str]]:
    files: Dict[str, Path] = {}
    missing: List[str] = []
    for raw in tracked_paths:
        rel = str(raw).strip().replace("\\", "/")
        if not rel:
            continue
        path = (repo_root / rel).resolve()
        if path.is_file():
            files[rel] = path
        else:
            missing.append(rel)
    return files, missing


def parse_entries(entries_raw: Any) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    entries: Dict[str, Dict[str, Any]] = {}
    violations: List[str] = []
    if not isinstance(entries_raw, list):
        return entries, ["provenance entries missing or invalid"]
    for item in entries_raw:
        if not isinstance(item, dict):
            violations.append("provenance entry is not an object")
            continue
        rel = str(item.get("path", "")).strip().replace("\\", "/")
        if not rel:
            violations.append("provenance entry path missing")
            continue
        if rel in entries:
            violations.append(f"duplicate provenance path: {rel}")
            continue
        entries[rel] = item
    if not entries:
        violations.append("provenance entries empty")
    return entries, violations


def build_provenance(repo_root: Path, tracked_paths: List[str], sign_key: str) -> Dict[str, Any]:
    files, missing = collect_files(repo_root, tracked_paths)
    if missing:
        raise FileNotFoundError("tracked path missing: " + ", ".join(sorted(missing)))

    entries: List[Dict[str, Any]] = []
    for rel in sorted(files.keys()):
        path = files[rel]
        entries.append(
            {
                "path": rel,
                "sha256": sha256_file(path),
                "size": int(path.stat().st_size),
            }
        )

    document: Dict[str, Any] = {
        "tool": "baseline_provenance_guard",
        "provenance_version": PROVENANCE_VERSION,
        "generated_at": now_iso(),
        "repo_root": ".",
        "repo_snapshot": get_repo_snapshot(repo_root),
        "tracked": {
            "paths": tracked_paths,
        },
        "entries": entries,
        "summary": {
            "file_count": len(entries),
        },
    }
    document["signature"] = build_signature(payload_without_signature(document), sign_key)
    return document


def verify_provenance(
    repo_root: Path,
    provenance: Dict[str, Any],
    strict_source_set: bool,
    max_age_seconds: int,
    require_git_head: bool,
    sign_key: str,
    require_hmac: bool,
) -> Dict[str, Any]:
    violations: List[str] = []
    signature_violations, signature_actual = verify_signature(provenance, sign_key=sign_key, require_hmac=require_hmac)
    violations.extend(signature_violations)

    tracked = provenance.get("tracked") if isinstance(provenance.get("tracked"), dict) else {}
    tracked_paths = tracked.get("paths") if isinstance(tracked.get("paths"), list) else list(DEFAULT_TRACKED_PATHS)
    tracked_paths = [str(x).strip().replace("\\", "/") for x in tracked_paths if str(x).strip()]

    entries, entry_violations = parse_entries(provenance.get("entries"))
    violations.extend(entry_violations)

    current_files, missing_current = collect_files(repo_root, tracked_paths)
    if strict_source_set:
        for rel in missing_current:
            violations.append(f"tracked path missing: {rel}")

    current_set = set(current_files.keys())
    entry_set = set(entries.keys())
    if strict_source_set:
        for rel in sorted(entry_set - current_set):
            violations.append(f"source-set missing file: {rel}")
        for rel in sorted(current_set - entry_set):
            violations.append(f"source-set unexpected file: {rel}")

    for rel in sorted(current_set & entry_set):
        expected_sha = str(entries[rel].get("sha256", "")).strip()
        if not expected_sha:
            violations.append(f"provenance sha256 missing: {rel}")
            continue
        actual_sha = sha256_file(current_files[rel])
        if actual_sha != expected_sha:
            violations.append(f"sha256 mismatch: {rel} expected={expected_sha} actual={actual_sha}")

    generated_at = parse_iso_datetime(str(provenance.get("generated_at", "")))
    age_seconds = None
    if generated_at is None:
        violations.append("generated_at missing or invalid")
    else:
        age_seconds = int((datetime.now(timezone.utc) - generated_at).total_seconds())
        if max_age_seconds > 0 and age_seconds > max_age_seconds:
            violations.append(
                f"provenance is stale: age_seconds={age_seconds} max_age_seconds={max_age_seconds}"
            )

    snapshot = provenance.get("repo_snapshot") if isinstance(provenance.get("repo_snapshot"), dict) else {}
    reported_head = str(snapshot.get("git_head", "")).strip()
    reported_head_available = bool(snapshot.get("git_head_available", False) and reported_head)

    current_snapshot = get_repo_snapshot(repo_root)
    current_head = str(current_snapshot.get("git_head", "")).strip()
    current_head_available = bool(current_snapshot.get("git_head_available", False) and current_head)

    if require_git_head and current_head_available:
        if not reported_head_available:
            violations.append("repo_snapshot.git_head missing while require_git_head=true")
        elif reported_head != current_head:
            violations.append(
                f"repo head mismatch: expected={current_head} actual={reported_head}"
            )

    report: Dict[str, Any] = {
        "tool": "baseline_provenance_guard",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "threshold": {
            "strict_source_set": bool(strict_source_set),
            "max_age_seconds": int(max_age_seconds),
            "require_git_head": bool(require_git_head),
            "require_hmac": bool(require_hmac),
        },
        "actual": {
            "tracked_count": len(tracked_paths),
            "entry_count": len(entries),
            "current_count": len(current_files),
            "age_seconds": age_seconds,
            "repo_snapshot": current_snapshot,
            "signature": signature_actual,
        },
        "violations": violations,
        "summary": {
            "passed": len(violations) == 0,
            "expected": len(entries),
            "current": len(current_files),
            "strict_source_set": bool(strict_source_set),
        },
    }
    return report


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_json(path: Path) -> Dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build/verify baseline provenance attestation.")
    sub = parser.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build")
    b.add_argument("--repo-root", required=True)
    b.add_argument("--provenance", required=True)
    b.add_argument("--tracked-path", action="append", default=[])
    b.add_argument("--sign-key-env", default=SIGN_KEY_ENV_DEFAULT)

    v = sub.add_parser("verify")
    v.add_argument("--repo-root", required=True)
    v.add_argument("--provenance", required=True)
    v.add_argument("--strict-source-set", default="true")
    v.add_argument("--max-age-seconds", type=int, default=0)
    v.add_argument("--require-git-head", default="false")
    v.add_argument("--sign-key-env", default=SIGN_KEY_ENV_DEFAULT)
    v.add_argument("--require-hmac", default="")
    v.add_argument("--out-json", default="")

    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    if not repo_root.is_dir():
        print(f"[baseline_provenance] FAIL: invalid repo_root: {repo_root}")
        return EXIT_INVALID_INPUT

    provenance_path = Path(args.provenance).expanduser()
    if not provenance_path.is_absolute():
        provenance_path = (repo_root / provenance_path).resolve()

    if args.command == "build":
        tracked_paths = args.tracked_path if args.tracked_path else list(DEFAULT_TRACKED_PATHS)
        tracked_paths = [str(x).strip().replace("\\", "/") for x in tracked_paths if str(x).strip()]
        if not tracked_paths:
            print("[baseline_provenance] FAIL: tracked path set is empty")
            return EXIT_INVALID_INPUT

        sign_key_env = str(args.sign_key_env or SIGN_KEY_ENV_DEFAULT).strip() or SIGN_KEY_ENV_DEFAULT
        if not sign_key_env.isidentifier():
            print(f"[baseline_provenance] FAIL: invalid sign key env name: {sign_key_env}")
            return EXIT_INVALID_INPUT
        sign_key = resolve_sign_key(sign_key_env)

        try:
            document = build_provenance(repo_root=repo_root, tracked_paths=tracked_paths, sign_key=sign_key)
        except FileNotFoundError as exc:
            print(f"[baseline_provenance] FAIL: {exc}")
            return EXIT_INVALID_INPUT

        write_json(provenance_path, document)
        signature = document.get("signature") if isinstance(document.get("signature"), dict) else {}
        scheme = str(signature.get("scheme", "sha256"))
        file_count = int(document.get("summary", {}).get("file_count", 0))
        print(f"[baseline_provenance] BUILD: provenance={provenance_path} files={file_count} signature_scheme={scheme}")
        return 0

    if not provenance_path.is_file():
        print(f"[baseline_provenance] FAIL: provenance not found: {provenance_path}")
        return EXIT_INVALID_INPUT

    sign_key_env = str(args.sign_key_env or SIGN_KEY_ENV_DEFAULT).strip() or SIGN_KEY_ENV_DEFAULT
    if not sign_key_env.isidentifier():
        print(f"[baseline_provenance] FAIL: invalid sign key env name: {sign_key_env}")
        return EXIT_INVALID_INPUT

    sign_key = resolve_sign_key(sign_key_env)
    require_hmac = resolve_require_hmac(args.require_hmac, sign_key_present=bool(sign_key))
    if require_hmac and not sign_key:
        print(f"[baseline_provenance] FAIL: require_hmac=true but sign key env '{sign_key_env}' is empty")
        return EXIT_INVALID_INPUT

    report = verify_provenance(
        repo_root=repo_root,
        provenance=load_json(provenance_path),
        strict_source_set=parse_bool(args.strict_source_set, default=True),
        max_age_seconds=max(0, int(args.max_age_seconds)),
        require_git_head=parse_bool(args.require_git_head, default=False),
        sign_key=sign_key,
        require_hmac=require_hmac,
    )

    out_json = str(args.out_json or "").strip()
    if out_json:
        out_path = Path(out_json).expanduser()
        if not out_path.is_absolute():
            out_path = (repo_root / out_path).resolve()
        write_json(out_path, report)

    summary = report.get("summary", {}) if isinstance(report, dict) else {}
    passed = bool(summary.get("passed", False))
    expected = int(summary.get("expected", 0))
    current = int(summary.get("current", 0))
    strict_source_set = bool(summary.get("strict_source_set", False))
    violations = report.get("violations", []) if isinstance(report, dict) else []
    signature = report.get("actual", {}).get("signature", {}) if isinstance(report.get("actual"), dict) else {}
    scheme = str(signature.get("scheme", ""))

    if passed:
        print(
            f"[baseline_provenance] PASS: expected={expected} current={current} "
            f"strict_source_set={strict_source_set} signature_scheme={scheme}"
        )
        return 0

    print("[baseline_provenance] FAIL")
    for item in violations:
        print(f"[baseline_provenance] violation: {item}")
    return EXIT_VERIFY_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
