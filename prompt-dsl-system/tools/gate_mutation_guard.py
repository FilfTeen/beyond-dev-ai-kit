#!/usr/bin/env python3
"""Mutation-resilience guard for key governance gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

EXIT_INVALID_INPUT = 2
EXIT_GUARD_FAIL = 40


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_cmd(cmd: List[str], env: Dict[str, str] | None = None) -> Dict[str, Any]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    except OSError as exc:
        return {
            "returncode": 127,
            "stdout": "",
            "stderr": str(exc),
        }
    return {
        "returncode": int(proc.returncode),
        "stdout": str(proc.stdout or ""),
        "stderr": str(proc.stderr or ""),
    }


def case_integrity_manifest_mutation(repo_root: Path, py: str, tmp_dir: Path) -> Dict[str, Any]:
    manifest = repo_root / "prompt-dsl-system/tools/kit_integrity_manifest.json"
    guard = repo_root / "prompt-dsl-system/tools/kit_integrity_guard.py"
    if not manifest.is_file() or not guard.is_file():
        return {"name": "integrity_manifest_mutation", "passed": False, "reason": "dependency missing"}

    bad_manifest = tmp_dir / "mutation_bad_manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    entries = data.get("entries")
    if isinstance(entries, list) and entries and isinstance(entries[0], dict):
        entries[0]["sha256"] = "0" * 64
    bad_manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    result = run_cmd(
        [
            py,
            str(guard),
            "verify",
            "--repo-root",
            str(repo_root),
            "--manifest",
            str(bad_manifest),
            "--strict-source-set",
            "true",
        ]
    )
    combined = (result.get("stdout", "") + "\n" + result.get("stderr", "")).strip()
    passed = result.get("returncode", 0) != 0 and "sha256 mismatch" in combined
    return {
        "name": "integrity_manifest_mutation",
        "passed": bool(passed),
        "returncode": int(result.get("returncode", 0)),
        "evidence": "sha256 mismatch" if passed else combined[:500],
    }


def case_trust_coverage_mutation(repo_root: Path, py: str, tmp_dir: Path) -> Dict[str, Any]:
    whitelist = repo_root / "prompt-dsl-system/tools/pipeline_trust_whitelist.json"
    guard = repo_root / "prompt-dsl-system/tools/pipeline_trust_coverage_guard.py"
    if not whitelist.is_file() or not guard.is_file():
        return {"name": "trust_coverage_mutation", "passed": False, "reason": "dependency missing"}

    bad_whitelist = tmp_dir / "mutation_bad_whitelist.json"
    data = json.loads(whitelist.read_text(encoding="utf-8"))
    entries = data.get("entries")
    if isinstance(entries, list):
        for item in entries:
            if isinstance(item, dict) and str(item.get("path", "")).endswith("pipeline_sql_oracle_to_dm8.md"):
                item["sha256"] = "e" * 64
                break

    signature = data.get("signature")
    if isinstance(signature, dict):
        payload = {k: data[k] for k in sorted(data.keys()) if k != "signature"}
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        signature["scheme"] = "sha256"
        signature["content_sha256"] = hashlib.sha256(canonical).hexdigest()
        signature.pop("hmac_sha256", None)
        signature.pop("key_id", None)

    bad_whitelist.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    result = run_cmd(
        [
            py,
            str(guard),
            "--repo-root",
            str(repo_root),
            "--whitelist",
            str(bad_whitelist),
            "--strict-source-set",
            "true",
            "--require-active",
            "true",
        ]
    )
    combined = (result.get("stdout", "") + "\n" + result.get("stderr", "")).strip()
    passed = result.get("returncode", 0) != 0 and "sha256 mismatch" in combined
    return {
        "name": "trust_coverage_mutation",
        "passed": bool(passed),
        "returncode": int(result.get("returncode", 0)),
        "evidence": "sha256 mismatch" if passed else combined[:500],
    }


def case_governance_doc_mutation(repo_root: Path, py: str, tmp_dir: Path) -> Dict[str, Any]:
    guard = repo_root / "prompt-dsl-system/tools/governance_consistency_guard.py"
    matrix = repo_root / "prompt-dsl-system/00_conventions/COMPLIANCE_MATRIX.md"
    if not guard.is_file() or not matrix.is_file():
        return {"name": "governance_doc_mutation", "passed": False, "reason": "dependency missing"}

    bad_matrix = tmp_dir / "mutation_bad_matrix.md"
    text = matrix.read_text(encoding="utf-8")
    mutated = text.replace("R16~R58", "R16~R57", 1)
    if mutated == text:
        mutated = text.replace("R16~R61", "R16~R60", 1)
    bad_matrix.write_text(mutated, encoding="utf-8")

    result = run_cmd(
        [
            py,
            str(guard),
            "--repo-root",
            str(repo_root),
            "--matrix",
            str(bad_matrix),
        ]
    )
    combined = (result.get("stdout", "") + "\n" + result.get("stderr", "")).strip()
    passed = result.get("returncode", 0) != 0 and "title max mismatch" in combined
    return {
        "name": "governance_doc_mutation",
        "passed": bool(passed),
        "returncode": int(result.get("returncode", 0)),
        "evidence": "title max mismatch" if passed else combined[:500],
    }


def case_tool_syntax_mutation(repo_root: Path, py: str, tmp_dir: Path) -> Dict[str, Any]:
    guard = repo_root / "prompt-dsl-system/tools/tool_syntax_guard.py"
    if not guard.is_file():
        return {"name": "tool_syntax_mutation", "passed": False, "reason": "dependency missing"}

    unique_suffix = uuid4().hex[:12]
    rel_bad_shell = f"prompt-dsl-system/tools/_mutation_tmp_bad_{unique_suffix}.sh"
    bad_shell = repo_root / rel_bad_shell
    bad_shell.write_text("#!/usr/bin/env bash\nif [ 1 -eq 1 ]; then\n  echo bad\n", encoding="utf-8")
    try:
        result = run_cmd(
            [
                py,
                str(guard),
                "--repo-root",
                str(repo_root),
                "--python-glob",
                "prompt-dsl-system/tools/governance_consistency_guard.py",
                "--shell-file",
                rel_bad_shell,
                "--strict-source-set",
                "true",
            ]
        )
    finally:
        try:
            bad_shell.unlink()
        except OSError:
            pass

    combined = (result.get("stdout", "") + "\n" + result.get("stderr", "")).strip()
    passed = result.get("returncode", 0) != 0 and "shell syntax error" in combined
    return {
        "name": "tool_syntax_mutation",
        "passed": bool(passed),
        "returncode": int(result.get("returncode", 0)),
        "evidence": "shell syntax error" if passed else combined[:500],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Mutation-resilience guard for governance gates.")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--out-json", default="")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    if not repo_root.is_dir():
        print(f"[mutation_guard] FAIL: invalid repo_root: {repo_root}")
        return EXIT_INVALID_INPUT

    py = os.environ.get("PYTHON_BIN", "") or subprocess.run(["which", "python3"], capture_output=True, text=True).stdout.strip() or "/usr/bin/python3"

    with tempfile.TemporaryDirectory(prefix="hz_mutation_guard_") as temp_dir:
        tmp_path = Path(temp_dir).resolve()
        cases = [
            case_integrity_manifest_mutation(repo_root, py, tmp_path),
            case_trust_coverage_mutation(repo_root, py, tmp_path),
            case_governance_doc_mutation(repo_root, py, tmp_path),
            case_tool_syntax_mutation(repo_root, py, tmp_path),
        ]

    blocked = sum(1 for c in cases if bool(c.get("passed", False)))
    total = len(cases)
    passed = blocked == total

    report: Dict[str, Any] = {
        "tool": "gate_mutation_guard",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "summary": {
            "passed": bool(passed),
            "cases_total": total,
            "cases_blocked": blocked,
            "cases_failed": total - blocked,
        },
        "cases": cases,
    }

    out_json = str(args.out_json or "").strip()
    if out_json:
        out_path = Path(out_json).expanduser()
        if not out_path.is_absolute():
            out_path = (repo_root / out_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if passed:
        print(f"[mutation_guard] PASS blocked={blocked}/{total}")
        return 0

    print(f"[mutation_guard] FAIL blocked={blocked}/{total}")
    for case in cases:
        if not bool(case.get("passed", False)):
            print(f"[mutation_guard] case_fail: {case.get('name')} evidence={case.get('evidence', case.get('reason', '-'))}")
    return EXIT_GUARD_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
