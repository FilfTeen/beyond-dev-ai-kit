#!/usr/bin/env python3
"""HMAC strict-mode smoke tests for baseline integrity/trust guards."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

EXIT_SMOKE_FAIL = 52


def run_cmd(cmd: List[str], env: Dict[str, str]) -> Tuple[int, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    merged = []
    if proc.stdout:
        merged.append(proc.stdout.strip())
    if proc.stderr:
        merged.append(proc.stderr.strip())
    return proc.returncode, "\n".join(x for x in merged if x).strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run HMAC strict-mode smoke tests")
    parser.add_argument("--repo-root", default=".", help="Repository root path")
    parser.add_argument(
        "--pipeline",
        default="prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_kit_self_upgrade.md",
        help="Pipeline path for trust verify",
    )
    parser.add_argument(
        "--key-env",
        default="HONGZHI_BASELINE_SIGN_KEY",
        help="Environment variable name used by guards to resolve sign key",
    )
    parser.add_argument(
        "--test-key",
        default="hongzhi_hmac_smoke_key_v1",
        help="Temporary key value used in smoke tests",
    )
    parser.add_argument("--out-json", default="", help="Optional output report path")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    repo_root = Path(args.repo_root).expanduser().resolve()
    if not repo_root.is_dir():
        print(f"[hmac_smoke] FAIL: invalid repo-root: {repo_root}")
        return 2

    tools_dir = repo_root / "prompt-dsl-system" / "tools"
    kit_guard = tools_dir / "kit_integrity_guard.py"
    trust_guard = tools_dir / "pipeline_trust_guard.py"
    pipeline_path = (repo_root / args.pipeline).resolve()
    if not kit_guard.is_file():
        print(f"[hmac_smoke] FAIL: missing guard: {kit_guard}")
        return 2
    if not trust_guard.is_file():
        print(f"[hmac_smoke] FAIL: missing guard: {trust_guard}")
        return 2
    if not pipeline_path.is_file():
        print(f"[hmac_smoke] FAIL: missing pipeline: {pipeline_path}")
        return 2

    key_env = str(args.key_env).strip()
    if not key_env:
        print("[hmac_smoke] FAIL: key-env must not be empty")
        return 2

    results: List[Dict[str, Any]] = []

    def record(name: str, passed: bool, rc: int, output: str) -> None:
        results.append(
            {
                "name": name,
                "passed": bool(passed),
                "rc": int(rc),
                "output": output,
            }
        )

    with tempfile.TemporaryDirectory(prefix="hz_hmac_smoke_") as tmp_dir:
        tmp = Path(tmp_dir)
        manifest_path = tmp / "manifest_hmac.json"
        whitelist_path = tmp / "whitelist_hmac.json"

        env_ok = os.environ.copy()
        env_ok[key_env] = args.test_key
        env_wrong = os.environ.copy()
        env_wrong[key_env] = f"{args.test_key}_wrong"
        env_missing = os.environ.copy()
        env_missing.pop(key_env, None)

        # 1) Build HMAC manifest
        rc, out = run_cmd(
            [
                sys.executable,
                str(kit_guard),
                "build",
                "--repo-root",
                str(repo_root),
                "--manifest",
                str(manifest_path),
                "--sign-key-env",
                key_env,
            ],
            env_ok,
        )
        record("manifest_build_hmac", rc == 0, rc, out)

        # 2) Verify HMAC manifest with correct key
        rc, out = run_cmd(
            [
                sys.executable,
                str(kit_guard),
                "verify",
                "--repo-root",
                str(repo_root),
                "--manifest",
                str(manifest_path),
                "--strict-source-set",
                "true",
                "--sign-key-env",
                key_env,
                "--require-hmac",
                "true",
            ],
            env_ok,
        )
        record("manifest_verify_hmac_correct_key", rc == 0, rc, out)

        # 3) Verify HMAC manifest with wrong key should fail
        rc, out = run_cmd(
            [
                sys.executable,
                str(kit_guard),
                "verify",
                "--repo-root",
                str(repo_root),
                "--manifest",
                str(manifest_path),
                "--strict-source-set",
                "true",
                "--sign-key-env",
                key_env,
                "--require-hmac",
                "true",
            ],
            env_wrong,
        )
        record(
            "manifest_verify_hmac_wrong_key_blocked",
            rc != 0 and ("hmac mismatch" in out or "FAIL" in out),
            rc,
            out,
        )

        # 4) Build HMAC whitelist
        rc, out = run_cmd(
            [
                sys.executable,
                str(trust_guard),
                "build",
                "--repo-root",
                str(repo_root),
                "--whitelist",
                str(whitelist_path),
                "--sign-key-env",
                key_env,
            ],
            env_ok,
        )
        record("whitelist_build_hmac", rc == 0, rc, out)

        # 5) Verify HMAC whitelist with correct key
        rc, out = run_cmd(
            [
                sys.executable,
                str(trust_guard),
                "verify",
                "--repo-root",
                str(repo_root),
                "--pipeline",
                str(pipeline_path),
                "--whitelist",
                str(whitelist_path),
                "--strict-source-set",
                "true",
                "--require-active",
                "true",
                "--sign-key-env",
                key_env,
                "--require-hmac",
                "true",
            ],
            env_ok,
        )
        record("whitelist_verify_hmac_correct_key", rc == 0, rc, out)

        # 6) Verify HMAC whitelist without key should fail
        rc, out = run_cmd(
            [
                sys.executable,
                str(trust_guard),
                "verify",
                "--repo-root",
                str(repo_root),
                "--pipeline",
                str(pipeline_path),
                "--whitelist",
                str(whitelist_path),
                "--strict-source-set",
                "true",
                "--require-active",
                "true",
                "--sign-key-env",
                key_env,
                "--require-hmac",
                "true",
            ],
            env_missing,
        )
        record(
            "whitelist_verify_hmac_missing_key_blocked",
            rc != 0 and ("hmac sign key missing" in out or "FAIL" in out),
            rc,
            out,
        )

    passed = all(bool(item.get("passed")) for item in results)
    report = {
        "tool": "hmac_strict_smoke",
        "repo_root": str(repo_root),
        "key_env": key_env,
        "passed": passed,
        "checks_total": len(results),
        "checks_passed": sum(1 for item in results if bool(item.get("passed"))),
        "checks": results,
    }

    if args.out_json:
        out_path = Path(args.out_json).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if passed:
        print(
            "[hmac_smoke] PASS: "
            f"checks={report['checks_passed']}/{report['checks_total']} key_env={key_env}"
        )
        return 0

    print("[hmac_smoke] FAIL")
    for item in results:
        if bool(item.get("passed")):
            continue
        print(f"[hmac_smoke] check_fail: {item.get('name')} rc={item.get('rc')}")
        output = str(item.get("output", "")).strip()
        if output:
            print(f"[hmac_smoke] detail: {output}")
    return EXIT_SMOKE_FAIL


if __name__ == "__main__":
    raise SystemExit(main())

