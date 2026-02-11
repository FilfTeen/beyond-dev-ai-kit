#!/usr/bin/env python3
"""Resolve move-plan destination conflicts with explicit strategies.

Safe by default: plan-only unless --mode apply with --yes and --dry-run false.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_bool(value: Any, default: bool) -> bool:
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


def normalize_rel(path_text: str) -> str:
    text = str(path_text).replace("\\", "/").strip()
    while text.startswith("./"):
        text = text[2:]
    return text


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def resolve_under_repo(repo_root: Path, path_arg: str, require_exists: bool = False) -> Path:
    p = Path(path_arg)
    if not p.is_absolute():
        p = (repo_root / p).resolve()
    else:
        p = p.resolve()

    try:
        p.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError(f"Path must be under repo root: {path_arg}") from exc

    if require_exists and not p.exists():
        raise ValueError(f"Path does not exist: {path_arg}")
    return p


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def detect_vcs(repo_root: Path, move_report: Dict[str, Any]) -> str:
    vcs = str(move_report.get("vcs", "")).strip().lower()
    if vcs in {"git", "svn", "none"}:
        return vcs
    if (repo_root / ".git").exists():
        return "git"
    if (repo_root / ".svn").exists():
        return "svn"
    return "none"


def sanitize_token(text: str) -> str:
    src = normalize_rel(text)
    while src.startswith("../"):
        src = src[3:]
    token = src.replace("/", "__")
    if len(token) <= 160:
        return token
    ext = ""
    base = Path(src).name
    if "." in base and not base.startswith("."):
        ext = "." + base.split(".")[-1]
    hash8 = hashlib.sha1(src.encode("utf-8")).hexdigest()[:8]
    keep = max(16, 160 - len(ext) - 9)
    return f"{token[:keep]}_{hash8}{ext}"


def hash8(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def parse_conflicts(move_report: Dict[str, Any], module_rel: str) -> List[Dict[str, Any]]:
    items_raw = move_report.get("items")
    items = items_raw if isinstance(items_raw, list) else []

    conflicts: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        src = str(item.get("src", "")).strip()
        if not src:
            continue
        dst = item.get("dst")
        dst_text = str(dst).strip() if isinstance(dst, str) else ""
        can_move = bool(item.get("can_move", False))
        deny_reason = str(item.get("deny_reason", "")).strip().lower()
        flags_raw = item.get("risk_flags")
        flags = [str(x).strip().lower() for x in flags_raw] if isinstance(flags_raw, list) else []

        is_conflict = False
        if "dst_exists" in flags:
            is_conflict = True
        elif not can_move and "dst exists" in deny_reason:
            is_conflict = True

        if not is_conflict:
            continue

        dst_base = dst_text
        if not dst_base:
            dst_base = f"{module_rel.rstrip('/')}/_imports/{sanitize_token(src)}"

        rename_dst = f"{dst_base}.moved.{hash8(src + '|' + dst_base)}"
        bucket_dst = (
            f"{module_rel.rstrip('/')}/_imports_conflicts/{sanitize_token(src)}/{Path(src).name}"
        )

        conflicts.append(
            {
                "src": normalize_rel(src),
                "dst_current": normalize_rel(dst_base),
                "violation_type": str(item.get("violation_type", "outside_module")),
                "risk_flags": sorted(set(flags)),
                "deny_reason": str(item.get("deny_reason", "")).strip() or None,
                "rename_suffix_dst": normalize_rel(rename_dst),
                "imports_bucket_dst": normalize_rel(bucket_dst),
                "needs_followup": [
                    "update references/imports",
                    "review build/resource scan paths",
                    "re-run debug-guard and validate",
                ],
            }
        )

    return conflicts


def command_for_move(vcs: str, src: str, dst: str) -> str:
    src_q = shlex.quote(src)
    dst_q = shlex.quote(dst)
    if vcs == "git":
        return f"git mv {src_q} {dst_q}"
    if vcs == "svn":
        return f"svn mv {src_q} {dst_q}"
    return f"mv {src_q} {dst_q}"


def build_strategy_script(repo_root: Path, vcs: str, mappings: Sequence[Tuple[str, str]], abort_only: bool) -> str:
    lines: List[str] = []
    lines.append("#!/usr/bin/env bash")
    lines.append("set -euo pipefail")
    lines.append(f"cd {shlex.quote(str(repo_root))}")
    lines.append("")

    if abort_only:
        lines.append('echo "[ABORT] conflict strategy abort selected; no files moved." >&2')
        lines.append("exit 2")
        return "\n".join(lines) + "\n"

    for src, dst in mappings:
        dst_parent = str(Path(dst).parent).replace("\\", "/")
        src_q = shlex.quote(src)
        dst_q = shlex.quote(dst)
        dst_parent_q = shlex.quote(dst_parent)
        lines.append(f"if [ ! -e {src_q} ] && [ ! -L {src_q} ]; then")
        lines.append(f"  echo \"[ERROR] source missing: {src}\" >&2")
        lines.append("  exit 2")
        lines.append("fi")
        lines.append(f"mkdir -p {dst_parent_q}")
        lines.append(f"if [ -e {dst_q} ] || [ -L {dst_q} ]; then")
        lines.append(f"  echo \"[ERROR] destination exists: {dst}\" >&2")
        lines.append("  exit 2")
        lines.append("fi")
        lines.append(command_for_move(vcs, src, dst))
        lines.append("")

    return "\n".join(lines) + "\n"


def read_ack_token(token_json_path: Path) -> Optional[str]:
    data = load_json(token_json_path)
    token = data.get("token")
    if isinstance(token, str) and token.strip():
        return token.strip()
    if isinstance(token, dict):
        v = token.get("value")
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def run_risk_gate(
    repo_root: Path,
    output_dir: Path,
    guard_report: Path,
    loop_report: Path,
    move_report: Path,
    threshold: str,
    ack: Optional[str],
) -> int:
    script = (repo_root / "prompt-dsl-system" / "tools" / "risk_gate.py").resolve()
    if not script.exists():
        print(f"risk_gate.py not found: {script}", file=sys.stderr)
        return 2

    token_txt = (output_dir / "RISK_GATE_TOKEN.txt").resolve()
    token_json = (output_dir / "RISK_GATE_TOKEN.json").resolve()
    report_json = (output_dir / "risk_gate_report.json").resolve()

    cmd = [
        sys.executable,
        str(script),
        "--repo-root",
        str(repo_root),
        "--guard-report",
        to_repo_relative(guard_report, repo_root),
        "--loop-report",
        to_repo_relative(loop_report, repo_root),
        "--move-report",
        to_repo_relative(move_report, repo_root),
        "--threshold",
        str(threshold).upper(),
        "--token-out",
        to_repo_relative(token_txt, repo_root),
        "--token-json-out",
        to_repo_relative(token_json, repo_root),
        "--json-out",
        to_repo_relative(report_json, repo_root),
        "--mode",
        "check",
        "--consume-on-pass",
        "true",
    ]
    if ack:
        cmd.extend(["--ack", ack])

    proc = subprocess.run(cmd, cwd=str(repo_root), text=True)
    return proc.returncode


def write_apply_log(
    path: Path,
    strategy: str,
    script_path: Path,
    mode: str,
    executed: bool,
    ok: bool,
    message: str,
    stdout_text: str,
    stderr_text: str,
) -> None:
    lines: List[str] = []
    lines.append("# conflict_apply_log")
    lines.append("")
    lines.append(f"- generated_at: {now_iso()}")
    lines.append(f"- mode: {mode}")
    lines.append(f"- strategy: {strategy}")
    lines.append(f"- script: {script_path}")
    lines.append(f"- executed: {str(executed).lower()}")
    lines.append(f"- result: {'success' if ok else 'failed'}")
    lines.append(f"- message: {message}")
    lines.append("")
    lines.append("## stdout")
    lines.append("```")
    lines.append(stdout_text.strip() if stdout_text.strip() else "(empty)")
    lines.append("```")
    lines.append("")
    lines.append("## stderr")
    lines.append("```")
    lines.append(stderr_text.strip() if stderr_text.strip() else "(empty)")
    lines.append("```")
    lines.append("")
    lines.append("## Next")
    lines.append("- ./prompt-dsl-system/tools/run.sh debug-guard -r . -m <MODULE_PATH>")
    lines.append("- ./prompt-dsl-system/tools/run.sh validate -r .")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_moves_mapping(path: Path, strategy: str, mappings: Sequence[Dict[str, Any]]) -> None:
    payload = {
        "generated_at": now_iso(),
        "strategy": strategy,
        "mappings": list(mappings),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_followup_scanner(
    repo_root: Path,
    scanner_script: Path,
    moves_file: Path,
    target_report: Path,
    target_checklist: Path,
    mode: str,
    max_hits_per_move: int = 50,
) -> Tuple[bool, str]:
    if not scanner_script.exists():
        return False, f"followup scanner not found: {scanner_script}"

    temp_dir = target_report.parent / f"_followup_tmp_{target_report.stem}"
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(scanner_script),
        "--repo-root",
        str(repo_root),
        "--moves",
        to_repo_relative(moves_file, repo_root),
        "--output-dir",
        to_repo_relative(temp_dir, repo_root),
        "--max-hits-per-move",
        str(max_hits_per_move),
        "--mode",
        mode,
    ]
    proc = subprocess.run(cmd, cwd=str(repo_root), text=True, capture_output=True)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or "unknown error"
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False, f"followup scan failed: {detail}"

    generated_report = temp_dir / "followup_scan_report.json"
    generated_checklist = temp_dir / "followup_checklist.md"
    if not generated_report.exists() or not generated_checklist.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False, "followup scanner did not produce expected files"

    target_report.parent.mkdir(parents=True, exist_ok=True)
    target_checklist.parent.mkdir(parents=True, exist_ok=True)
    generated_report.replace(target_report)
    generated_checklist.replace(target_checklist)
    shutil.rmtree(temp_dir, ignore_errors=True)
    return True, "ok"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate/execute move conflict resolution strategies")
    p.add_argument("--repo-root", required=True)
    p.add_argument("--module-path", required=True)
    p.add_argument("--move-report", default="prompt-dsl-system/tools/move_report.json")
    p.add_argument("--output-dir", default="prompt-dsl-system/tools")
    p.add_argument("--mode", choices=["plan", "apply"], default="plan")
    p.add_argument("--strategy", choices=["rename_suffix", "imports_bucket", "abort"], default="abort")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--dry-run", default="true")
    p.add_argument("--ack")
    p.add_argument("--ack-file")
    p.add_argument("--ack-latest", action="store_true")
    p.add_argument("--risk-threshold", default="HIGH")
    p.add_argument("--guard-report", default="prompt-dsl-system/tools/guard_report.json")
    p.add_argument("--loop-report", default="prompt-dsl-system/tools/loop_diagnostics.json")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        print(f"Invalid repo root: {repo_root}", file=sys.stderr)
        return 2

    try:
        module_path = resolve_under_repo(repo_root, args.module_path, require_exists=True)
        move_report_path = resolve_under_repo(repo_root, args.move_report, require_exists=True)
        output_dir = resolve_under_repo(repo_root, args.output_dir, require_exists=False)
        guard_report = resolve_under_repo(repo_root, args.guard_report, require_exists=False)
        loop_report = resolve_under_repo(repo_root, args.loop_report, require_exists=False)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)

    module_rel = to_repo_relative(module_path, repo_root)
    move_report = load_json(move_report_path)
    vcs = detect_vcs(repo_root, move_report)
    conflicts = parse_conflicts(move_report, module_rel)

    rename_script = (output_dir / "conflict_plan_strategy_rename_suffix.sh").resolve()
    imports_script = (output_dir / "conflict_plan_strategy_imports_bucket.sh").resolve()
    abort_script = (output_dir / "conflict_plan_strategy_abort.sh").resolve()
    plan_md = (output_dir / "conflict_plan.md").resolve()
    plan_json = (output_dir / "conflict_plan.json").resolve()
    apply_log = (output_dir / "conflict_apply_log.md").resolve()
    followup_scanner_script = (repo_root / "prompt-dsl-system" / "tools" / "ref_followup_scanner.py").resolve()

    rename_pairs = [(c["src"], c["rename_suffix_dst"]) for c in conflicts]
    imports_pairs = [(c["src"], c["imports_bucket_dst"]) for c in conflicts]
    rename_mappings = [
        {
            "src": c["src"],
            "dst": c["rename_suffix_dst"],
            "kind": "rename_suffix",
            "notes": c.get("needs_followup", []),
        }
        for c in conflicts
    ]
    imports_mappings = [
        {
            "src": c["src"],
            "dst": c["imports_bucket_dst"],
            "kind": "imports_bucket",
            "notes": c.get("needs_followup", []),
        }
        for c in conflicts
    ]
    abort_mappings: List[Dict[str, Any]] = []

    strategy_mappings: Dict[str, List[Dict[str, Any]]] = {
        "rename_suffix": rename_mappings,
        "imports_bucket": imports_mappings,
        "abort": abort_mappings,
    }

    rename_script.write_text(build_strategy_script(repo_root, vcs, rename_pairs, abort_only=False), encoding="utf-8")
    imports_script.write_text(build_strategy_script(repo_root, vcs, imports_pairs, abort_only=False), encoding="utf-8")
    abort_script.write_text(build_strategy_script(repo_root, vcs, [], abort_only=True), encoding="utf-8")
    rename_script.chmod(0o755)
    imports_script.chmod(0o755)
    abort_script.chmod(0o755)

    followup_outputs: Dict[str, Dict[str, str]] = {}
    for strategy in ("rename_suffix", "imports_bucket", "abort"):
        mapping_path = (output_dir / f"moves_mapping_{strategy}.json").resolve()
        report_path = (output_dir / f"followup_scan_report_{strategy}.json").resolve()
        checklist_path = (output_dir / f"followup_checklist_{strategy}.md").resolve()

        write_moves_mapping(mapping_path, strategy, strategy_mappings[strategy])
        scan_ok, scan_message = run_followup_scanner(
            repo_root=repo_root,
            scanner_script=followup_scanner_script,
            moves_file=mapping_path,
            target_report=report_path,
            target_checklist=checklist_path,
            mode="plan",
        )
        followup_outputs[strategy] = {
            "moves_mapping": to_repo_relative(mapping_path, repo_root),
            "followup_scan_report": to_repo_relative(report_path, repo_root),
            "followup_checklist": to_repo_relative(checklist_path, repo_root),
            "followup_scan_ok": str(scan_ok).lower(),
            "followup_scan_message": scan_message,
        }

    strategy_meta = {
        "rename_suffix": {
            "script": to_repo_relative(rename_script, repo_root),
            "description": "move to dst.moved.<hash8> to avoid overwrite",
            "count": len(rename_pairs),
            "mappings": rename_mappings,
            **followup_outputs["rename_suffix"],
        },
        "imports_bucket": {
            "script": to_repo_relative(imports_script, repo_root),
            "description": "move to module/_imports_conflicts/... to avoid structural collisions",
            "count": len(imports_pairs),
            "mappings": imports_mappings,
            **followup_outputs["imports_bucket"],
        },
        "abort": {
            "script": to_repo_relative(abort_script, repo_root),
            "description": "stop and require manual intervention",
            "count": len(conflicts),
            "mappings": abort_mappings,
            **followup_outputs["abort"],
        },
    }

    plan_obj = {
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "module_path": str(module_path),
        "module_path_normalized": module_rel,
        "vcs": vcs,
        "move_report": to_repo_relative(move_report_path, repo_root),
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
        "strategies": strategy_meta,
    }
    plan_json.write_text(json.dumps(plan_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    md: List[str] = []
    md.append("# conflict_plan")
    md.append("")
    md.append(f"- generated_at: {plan_obj['generated_at']}")
    md.append(f"- module_path_normalized: {module_rel}")
    md.append(f"- move_report: {to_repo_relative(move_report_path, repo_root)}")
    md.append(f"- conflict_count: {len(conflicts)}")
    md.append("")

    if not conflicts:
        md.append("## Status")
        md.append("- no conflicts")
    else:
        md.append("## Conflicts")
        for idx, c in enumerate(conflicts, start=1):
            md.append(f"{idx}. `{c['src']}` -> current dst `{c['dst_current']}`")
            md.append(f"   - deny_reason: {c['deny_reason'] or 'n/a'}")
            md.append(f"   - risk_flags: {', '.join(c['risk_flags']) if c['risk_flags'] else 'none'}")
            md.append(f"   - rename_suffix: `{c['rename_suffix_dst']}`")
            md.append(f"   - imports_bucket: `{c['imports_bucket_dst']}`")

    md.append("")
    md.append("## Strategy Scripts")
    md.append(f"- rename_suffix: `{strategy_meta['rename_suffix']['script']}`")
    md.append(f"- imports_bucket: `{strategy_meta['imports_bucket']['script']}`")
    md.append(f"- abort: `{strategy_meta['abort']['script']}`")
    md.append("")
    md.append("## 引用修复清单（静态扫描）")
    md.append("- 说明：以下清单仅为静态候选结果，不做业务推断，必须人工确认。")
    md.append(f"- rename_suffix checklist: `{strategy_meta['rename_suffix']['followup_checklist']}`")
    md.append(f"- rename_suffix report: `{strategy_meta['rename_suffix']['followup_scan_report']}`")
    md.append(f"- imports_bucket checklist: `{strategy_meta['imports_bucket']['followup_checklist']}`")
    md.append(f"- imports_bucket report: `{strategy_meta['imports_bucket']['followup_scan_report']}`")
    md.append(f"- abort checklist: `{strategy_meta['abort']['followup_checklist']}`")
    md.append(f"- abort report: `{strategy_meta['abort']['followup_scan_report']}`")
    md.append("")
    md.append("## Execute (safe defaults)")
    md.append("- plan only:")
    md.append(
        "  `./prompt-dsl-system/tools/run.sh resolve-move-conflicts -r . -m <MODULE_PATH> --strategy rename_suffix`"
    )
    md.append("- apply (requires ACK + explicit yes):")
    md.append(
        "  `./prompt-dsl-system/tools/run.sh resolve-move-conflicts -r . -m <MODULE_PATH> --strategy rename_suffix --mode apply --yes --dry-run false --ack-latest`"
    )
    plan_md.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"conflict_plan.md: {to_repo_relative(plan_md, repo_root)}")
    print(f"conflict_plan.json: {to_repo_relative(plan_json, repo_root)}")
    print(f"rename_suffix script: {to_repo_relative(rename_script, repo_root)}")
    print(f"imports_bucket script: {to_repo_relative(imports_script, repo_root)}")
    print(f"abort script: {to_repo_relative(abort_script, repo_root)}")
    print(f"followup checklist (rename_suffix): {strategy_meta['rename_suffix']['followup_checklist']}")
    print(f"followup checklist (imports_bucket): {strategy_meta['imports_bucket']['followup_checklist']}")
    print(f"followup checklist (abort): {strategy_meta['abort']['followup_checklist']}")

    if not conflicts:
        print("no conflicts detected")
        return 0

    if args.mode == "plan":
        return 0

    dry_run = parse_bool(args.dry_run, default=True)
    if not args.yes or dry_run:
        print(
            "apply requires --yes and --dry-run false; generated plans only.",
            file=sys.stderr,
        )
        return 2

    ack: Optional[str] = args.ack
    ack_file_path: Optional[Path] = None
    if args.ack_file:
        try:
            ack_file_path = resolve_under_repo(repo_root, args.ack_file, require_exists=True)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    elif args.ack_latest:
        ack_file_path = (output_dir / "RISK_GATE_TOKEN.json").resolve()
        if not ack_file_path.exists():
            fallback = (repo_root / "prompt-dsl-system" / "tools" / "RISK_GATE_TOKEN.json").resolve()
            if fallback.exists():
                ack_file_path = fallback

    if ack is None and ack_file_path is not None and ack_file_path.exists():
        ack = read_ack_token(ack_file_path)

    conflict_loop_report = (output_dir / "conflict_loop_high.json").resolve()
    conflict_loop_report.write_text(
        json.dumps(
            {
                "generated_at": now_iso(),
                "level": "HIGH",
                "triggers": [{"id": "MOVE_DST_EXISTS_CONFLICT", "severity": "HIGH"}],
                "recommendation": [
                    "resolve destination conflicts using selected move strategy before apply",
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    gate_rc = run_risk_gate(
        repo_root=repo_root,
        output_dir=output_dir,
        guard_report=guard_report,
        loop_report=conflict_loop_report,
        move_report=move_report_path,
        threshold=str(args.risk_threshold).upper(),
        ack=ack,
    )
    if gate_rc != 0:
        print("risk gate blocked conflict apply", file=sys.stderr)
        print(
            "Use ACK token and rerun: ./prompt-dsl-system/tools/run.sh resolve-move-conflicts -r . -m <MODULE_PATH> "
            f"--strategy {args.strategy} --mode apply --yes --dry-run false --ack-latest",
            file=sys.stderr,
        )
        return gate_rc

    selected_script: Path
    selected_mappings: List[Dict[str, Any]]
    if args.strategy == "rename_suffix":
        selected_script = rename_script
        selected_mappings = rename_mappings
    elif args.strategy == "imports_bucket":
        selected_script = imports_script
        selected_mappings = imports_mappings
    else:
        selected_script = abort_script
        selected_mappings = abort_mappings

    proc = subprocess.run(
        ["bash", str(selected_script)],
        cwd=str(repo_root),
        text=True,
        capture_output=True,
    )
    ok = proc.returncode == 0
    message = "applied" if ok else f"strategy script failed (exit {proc.returncode})"

    write_apply_log(
        path=apply_log,
        strategy=args.strategy,
        script_path=selected_script,
        mode=args.mode,
        executed=True,
        ok=ok,
        message=message,
        stdout_text=proc.stdout,
        stderr_text=proc.stderr,
    )
    print(f"conflict_apply_log.md: {to_repo_relative(apply_log, repo_root)}")
    if ok and selected_mappings:
        after_mapping_path = (output_dir / "moves_mapping_after_apply.json").resolve()
        after_report_path = (output_dir / "followup_scan_report_after_apply.json").resolve()
        after_checklist_path = (output_dir / "followup_checklist_after_apply.md").resolve()
        write_moves_mapping(after_mapping_path, f"{args.strategy}_after_apply", selected_mappings)
        after_ok, after_message = run_followup_scanner(
            repo_root=repo_root,
            scanner_script=followup_scanner_script,
            moves_file=after_mapping_path,
            target_report=after_report_path,
            target_checklist=after_checklist_path,
            mode="apply",
        )
        if after_ok:
            print(f"followup_checklist_after_apply: {to_repo_relative(after_checklist_path, repo_root)}")
            print(f"followup_scan_report_after_apply: {to_repo_relative(after_report_path, repo_root)}")
            print("next: 按 followup_checklist_after_apply.md 修复引用，再执行 debug-guard + validate")
            print(
                "next: ./prompt-dsl-system/tools/run.sh verify-followup-fixes -r . "
                f"--moves {to_repo_relative(after_mapping_path, repo_root)} "
                f"--scan-report {to_repo_relative(after_report_path, repo_root)}"
            )
        else:
            print(f"[WARN] post-apply followup scan failed: {after_message}", file=sys.stderr)
    print("recheck: ./prompt-dsl-system/tools/run.sh debug-guard -r . -m <MODULE_PATH>")
    print("recheck: ./prompt-dsl-system/tools/run.sh validate -r .")

    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
