#!/usr/bin/env python3
"""Verify residual old-reference tokens after move/patch operations (read-only)."""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

DEFAULT_INCLUDE_EXTS = [
    ".java",
    ".xml",
    ".yml",
    ".yaml",
    ".properties",
    ".json",
    ".js",
    ".ts",
    ".vue",
    ".html",
    ".xhtml",
    ".jsp",
    ".sql",
    ".md",
]

DEFAULT_EXCLUDE_DIRS = [
    ".git",
    "target",
    ".idea",
    ".vscode",
    "node_modules",
    "dist",
    "build",
    "out",
    "logs",
]


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


def normalize_ext(ext: str) -> str:
    text = str(ext).strip().lower()
    if not text:
        return ""
    if not text.startswith("."):
        text = "." + text
    return text


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def derive_java_fqcn(path_text: str) -> Optional[str]:
    rel = normalize_rel(path_text)
    m = re.search(r"(?:^|/)src/(?:main|test)/java/(.+)\.java$", rel)
    if not m:
        return None
    return m.group(1).replace("/", ".")


def limit_snippet(text: str, max_len: int = 200) -> str:
    cleaned = " ".join(text.strip().split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 3] + "..."


def parse_move_item(item: Dict[str, Any], kind: str) -> Optional[Dict[str, str]]:
    src = str(item.get("src", "")).strip()
    dst = str(item.get("dst", "")).strip()
    if not src or not dst:
        return None
    return {"src": normalize_rel(src), "dst": normalize_rel(dst), "kind": kind}


def parse_moves_payload(payload: Any) -> List[Dict[str, str]]:
    moves: List[Dict[str, str]] = []

    def append_item(item: Dict[str, Any], kind: str) -> None:
        parsed = parse_move_item(item, kind)
        if parsed is not None:
            moves.append(parsed)

    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                append_item(item, str(item.get("kind", "list")))
    elif isinstance(payload, dict):
        mappings = payload.get("mappings")
        if isinstance(mappings, list):
            default_kind = str(payload.get("strategy", payload.get("kind", "mapping")))
            for item in mappings:
                if isinstance(item, dict):
                    append_item(item, default_kind)

        items = payload.get("items")
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    append_item(item, str(item.get("kind", item.get("violation_type", "move_report"))))

        conflicts = payload.get("conflicts")
        if isinstance(conflicts, list):
            for item in conflicts:
                if not isinstance(item, dict):
                    continue
                src = str(item.get("src", "")).strip()
                if not src:
                    continue
                # conflict_plan may not have dst; use strategy mappings instead.
                for key, kind in (
                    ("rename_suffix_dst", "rename_suffix"),
                    ("imports_bucket_dst", "imports_bucket"),
                    ("dst_current", "conflict_current"),
                ):
                    dst = str(item.get(key, "")).strip()
                    if dst:
                        append_item({"src": src, "dst": dst}, kind)

        strategies = payload.get("strategies")
        if isinstance(strategies, dict):
            for strategy_name, strategy_meta in strategies.items():
                if not isinstance(strategy_meta, dict):
                    continue
                strategy_mappings = strategy_meta.get("mappings")
                if not isinstance(strategy_mappings, list):
                    continue
                for item in strategy_mappings:
                    if isinstance(item, dict):
                        append_item(item, str(strategy_name))

    dedup: List[Dict[str, str]] = []
    seen = set()
    for move in moves:
        key = (move["src"], move["dst"], move["kind"])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(move)
    return dedup


def build_tokens_from_moves(moves: Sequence[Dict[str, str]]) -> Dict[str, List[str]]:
    exact_paths: List[str] = []
    old_dirs: List[str] = []
    fqcn_hints: List[str] = []

    for move in moves:
        src = normalize_rel(move["src"])
        src_dir = str(Path(src).parent).replace("\\", "/")
        if src and src not in exact_paths:
            exact_paths.append(src)
        if src_dir and src_dir != "." and src_dir not in old_dirs:
            old_dirs.append(src_dir)
        fqcn = derive_java_fqcn(src)
        if fqcn and fqcn not in fqcn_hints:
            fqcn_hints.append(fqcn)

    return {
        "exact_paths": exact_paths,
        "old_dirs": old_dirs,
        "fqcn_hints": fqcn_hints,
    }


def merge_scan_tokens(groups: Dict[str, List[str]], scan_payload: Any) -> None:
    if not isinstance(scan_payload, dict):
        return
    moves = scan_payload.get("moves")
    if not isinstance(moves, list):
        return
    for move in moves:
        if not isinstance(move, dict):
            continue
        tokens = move.get("tokens")
        if not isinstance(tokens, list):
            continue
        for token in tokens:
            text = str(token).strip()
            if not text:
                continue
            if "/" in text and text not in groups["exact_paths"]:
                groups["exact_paths"].append(text)
            elif "." in text and text.count(".") >= 2 and text not in groups["fqcn_hints"]:
                groups["fqcn_hints"].append(text)
            elif text not in groups["old_dirs"]:
                groups["old_dirs"].append(text)


def merge_patch_plan_tokens(groups: Dict[str, List[str]], patch_plan_payload: Any) -> None:
    if not isinstance(patch_plan_payload, dict):
        return
    files = patch_plan_payload.get("files")
    if not isinstance(files, list):
        return
    for file_item in files:
        if not isinstance(file_item, dict):
            continue
        replacements = file_item.get("replacements")
        if not isinstance(replacements, list):
            continue
        for rep in replacements:
            if not isinstance(rep, dict):
                continue
            old = str(rep.get("from", "")).strip()
            if not old:
                continue
            if "/" in old and old not in groups["exact_paths"]:
                groups["exact_paths"].append(old)
            elif "." in old and old.count(".") >= 2 and old not in groups["fqcn_hints"]:
                groups["fqcn_hints"].append(old)
            elif old not in groups["old_dirs"]:
                groups["old_dirs"].append(old)


def normalize_pattern(pattern: str) -> str:
    p = pattern.strip()
    if not p:
        return p
    if p.startswith("**/") or "/" in p:
        return p
    return f"**/{p}"


def should_include_file(rel_path: str, include_exts: Sequence[str], exclude_dirs: Sequence[str]) -> bool:
    rel = normalize_rel(rel_path)
    parts = Path(rel).parts
    excluded = {x.lower() for x in exclude_dirs}
    for part in parts[:-1]:
        if part.lower() in excluded:
            return False
    ext = Path(rel).suffix.lower()
    return ext in include_exts


def build_rg_cmd(token: str, include_exts: Sequence[str], exclude_dirs: Sequence[str]) -> List[str]:
    cmd = ["rg", "--no-config", "--vimgrep", "-F", "-I", "--color", "never", "--hidden", "--no-messages"]
    for ext in include_exts:
        cmd.extend(["-g", normalize_pattern(f"*{ext}")])
    for ex in exclude_dirs:
        ex_name = ex.strip("/").strip()
        if ex_name:
            cmd.extend(["-g", f"!**/{ex_name}/**"])
    cmd.extend(["--", token, "."])
    return cmd


def build_grep_cmd(token: str, include_exts: Sequence[str], exclude_dirs: Sequence[str]) -> List[str]:
    cmd = ["grep", "-R", "-H", "-n", "-F", "--binary-files=without-match"]
    for ext in include_exts:
        cmd.append(f"--include=*{ext}")
    for ex in exclude_dirs:
        ex_name = ex.strip("/").strip()
        if ex_name:
            cmd.append(f"--exclude-dir={ex_name}")
    cmd.extend(["--", token, "."])
    return cmd


def parse_hit_line(line: str) -> Optional[Tuple[str, int, str]]:
    if not line or line.startswith("Binary file "):
        return None
    parts = line.split(":", 3)
    if len(parts) >= 4:
        path_text, line_text, _col_text, snippet = parts[0], parts[1], parts[2], parts[3]
    elif len(parts) >= 3:
        path_text, line_text, snippet = parts[0], parts[1], parts[2]
    else:
        return None
    if path_text.isdigit():
        return None
    try:
        line_no = int(line_text)
    except ValueError:
        return None
    return normalize_rel(path_text), line_no, snippet


def scan_token(
    repo_root: Path,
    scanner: str,
    token: str,
    include_exts: Sequence[str],
    exclude_dirs: Sequence[str],
) -> List[Tuple[str, int, str]]:
    rows: List[Tuple[str, int, str]] = []

    def collect(cmd: List[str]) -> Tuple[List[Tuple[str, int, str]], str]:
        proc = subprocess.run(cmd, cwd=str(repo_root), text=True, capture_output=True)
        out_rows: List[Tuple[str, int, str]] = []
        for line in (proc.stdout.splitlines() if proc.stdout else []):
            parsed = parse_hit_line(line)
            if parsed is None:
                continue
            out_rows.append(parsed)
        return out_rows, proc.stdout or ""

    if scanner == "rg":
        rg_rows, rg_stdout = collect(build_rg_cmd(token, include_exts, exclude_dirs))
        rows.extend(rg_rows)
        # Fallback: some local rg configs return line:col:text without file path.
        if not rows and rg_stdout.strip():
            grep_rows, _ = collect(build_grep_cmd(token, include_exts, exclude_dirs))
            rows.extend(grep_rows)
    elif scanner == "grep":
        grep_rows, _ = collect(build_grep_cmd(token, include_exts, exclude_dirs))
        rows.extend(grep_rows)
    else:
        return []

    return rows


def choose_scanner(use_rg: bool) -> str:
    if use_rg and shutil.which("rg"):
        return "rg"
    if shutil.which("grep"):
        return "grep"
    return "none"


def group_for_token(token: str, groups: Dict[str, List[str]]) -> str:
    if token in groups["exact_paths"]:
        return "exact_paths"
    if token in groups["fqcn_hints"]:
        return "fqcn_hints"
    return "old_dirs"


def status_from_hits(hits_total: int, hits: Sequence[Dict[str, Any]]) -> str:
    if hits_total == 0:
        return "PASS"
    critical = False
    for hit in hits:
        file_path = str(hit.get("file", ""))
        token_group = str(hit.get("token_group", ""))
        if ("src/main/java" in file_path or "/pages/" in file_path) and token_group in {"exact_paths", "fqcn_hints"}:
            critical = True
            break
    if hits_total > 20 or critical:
        return "FAIL"
    return "WARN"


def build_gate_hint(status: str) -> Tuple[bool, str]:
    s = str(status).strip().upper()
    if s == "FAIL":
        return True, "verify status FAIL; release gate acknowledgment is required before promote/apply commands."
    if s == "WARN":
        return False, "verify status WARN; gate is optional unless caller lowers verify threshold to WARN."
    return False, "verify status PASS; release gate is not required."


def build_recommended_actions(status: str) -> List[str]:
    if status == "PASS":
        return [
            "No residual old references found.",
            "Re-run debug-guard for boundary confirmation.",
            "Run validate and continue pipeline.",
        ]
    if status == "WARN":
        return [
            "Run apply-followup-fixes in plan mode and review patch.",
            "Manually review remaining low-volume hits.",
            "Re-run verify-followup-fixes after adjustments.",
        ]
    return [
        "Run apply-followup-fixes in plan mode, then apply with ACK if needed.",
        "Prioritize manual cleanup in src/main/java or pages paths.",
        "Re-run debug-guard and verify-followup-fixes before next run.",
    ]


def write_md_report(path: Path, report: Dict[str, Any]) -> None:
    summary = report.get("summary", {})
    status = summary.get("status", "WARN")
    top = report.get("top_findings", [])
    hits = report.get("hits", [])
    actions = report.get("recommended_actions", [])

    lines: List[str] = []
    lines.append("# followup_verify_report")
    lines.append("")
    lines.append(f"STATUS: **{status}**")
    lines.append("")
    lines.append(f"- generated_at: {report.get('generated_at')}")
    lines.append(f"- scanner: {report.get('scanner')}")
    lines.append(f"- mode: {report.get('mode')}")
    lines.append(f"- tokens_total: {summary.get('tokens_total', 0)}")
    lines.append(f"- tokens_with_hits: {summary.get('tokens_with_hits', 0)}")
    lines.append(f"- hits_total: {summary.get('hits_total', 0)}")
    lines.append(f"- total_hits_estimate: {summary.get('total_hits_estimate', 0)}")
    lines.append("")
    lines.append("## Top Tokens")
    if isinstance(top, list) and top:
        for item in top[:10]:
            lines.append(f"- `{item.get('token')}`: hits={item.get('hits', 0)}")
    else:
        lines.append("- no findings")
    lines.append("")
    lines.append("## Hit Samples")
    if isinstance(hits, list) and hits:
        for hit in hits[:20]:
            lines.append(
                f"- `{hit.get('file')}:{hit.get('line')}` token=`{hit.get('token')}` "
                f"group={hit.get('token_group')} :: {hit.get('snippet')}"
            )
        if len(hits) > 20:
            lines.append(f"- ... {len(hits) - 20} more hits in followup_verify_report.json")
    else:
        lines.append("- no residual hits")
    lines.append("")
    lines.append("## Next")
    if isinstance(actions, list):
        for action in actions[:3]:
            lines.append(f"- {action}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Verify residual old-reference tokens after follow-up fixes")
    p.add_argument("--repo-root", required=True)
    p.add_argument("--moves", required=True, help="conflict_plan.json / moves_mapping_*.json / move_report.json")
    p.add_argument("--scan-report", default="")
    p.add_argument("--patch-plan", default="")
    p.add_argument("--output-dir", default="prompt-dsl-system/tools")
    p.add_argument("--mode", choices=["post-move", "post-patch", "full"], default="full")
    p.add_argument("--max-hits", default="200")
    p.add_argument("--use-rg", default="true")
    p.add_argument("--exclude-dir", action="append", default=[])
    p.add_argument("--include-ext", action="append", default=[])
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        print(f"Invalid repo root: {repo_root}", file=sys.stderr)
        return 2

    moves_path = Path(args.moves)
    if not moves_path.is_absolute():
        moves_path = (repo_root / moves_path).resolve()
    if not moves_path.exists():
        print(f"moves file not found: {moves_path}", file=sys.stderr)
        return 2

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = (repo_root / output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    max_hits = int(args.max_hits) if str(args.max_hits).strip().isdigit() else 200
    max_hits = max(1, max_hits)
    use_rg = parse_bool(args.use_rg, default=True)

    include_exts = [normalize_ext(x) for x in (DEFAULT_INCLUDE_EXTS + list(args.include_ext or []))]
    include_exts = sorted({x for x in include_exts if x})
    exclude_dirs = sorted({str(x).strip() for x in (DEFAULT_EXCLUDE_DIRS + list(args.exclude_dir or [])) if str(x).strip()})
    try:
        output_rel = normalize_rel(output_dir.relative_to(repo_root).as_posix())
        output_base = Path(output_rel).name
        if output_base:
            exclude_dirs = sorted(set(exclude_dirs + [output_base]))
    except ValueError:
        pass

    try:
        moves_payload = load_json(moves_path)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"failed to parse moves JSON: {moves_path}: {exc}", file=sys.stderr)
        return 2
    moves = parse_moves_payload(moves_payload)
    groups = build_tokens_from_moves(moves)

    scan_path: Optional[Path] = None
    scan_payload: Any = None
    if str(args.scan_report).strip():
        scan_path = Path(str(args.scan_report).strip())
        if not scan_path.is_absolute():
            scan_path = (repo_root / scan_path).resolve()
        if scan_path.exists():
            try:
                scan_payload = load_json(scan_path)
            except (OSError, json.JSONDecodeError):
                scan_payload = None
            if scan_payload is not None:
                merge_scan_tokens(groups, scan_payload)

    patch_plan_path: Optional[Path] = None
    patch_plan_payload: Any = None
    if str(args.patch_plan).strip():
        patch_plan_path = Path(str(args.patch_plan).strip())
        if not patch_plan_path.is_absolute():
            patch_plan_path = (repo_root / patch_plan_path).resolve()
        if patch_plan_path.exists():
            try:
                patch_plan_payload = load_json(patch_plan_path)
            except (OSError, json.JSONDecodeError):
                patch_plan_payload = None
            if patch_plan_payload is not None:
                merge_patch_plan_tokens(groups, patch_plan_payload)

    ignored_files = {
        normalize_rel(moves_path.relative_to(repo_root).as_posix()),
    }
    if scan_path is not None:
        try:
            ignored_files.add(normalize_rel(scan_path.relative_to(repo_root).as_posix()))
        except ValueError:
            pass
    if patch_plan_path is not None:
        try:
            ignored_files.add(normalize_rel(patch_plan_path.relative_to(repo_root).as_posix()))
        except ValueError:
            pass

    # Dedup with stable ordering.
    for key in ("exact_paths", "old_dirs", "fqcn_hints"):
        seen = set()
        ordered: List[str] = []
        for token in groups[key]:
            t = str(token).strip()
            if not t or t in seen:
                continue
            seen.add(t)
            ordered.append(t)
        groups[key] = ordered

    all_tokens = groups["exact_paths"] + groups["old_dirs"] + groups["fqcn_hints"]
    scanner = choose_scanner(use_rg=use_rg)

    hits: List[Dict[str, Any]] = []
    hits_total_estimate = 0
    token_hits: Dict[str, int] = {}

    if scanner != "none":
        for token in all_tokens:
            rows = scan_token(
                repo_root=repo_root,
                scanner=scanner,
                token=token,
                include_exts=include_exts,
                exclude_dirs=exclude_dirs,
            )
            count_for_token = 0
            for rel_file, line_no, snippet in rows:
                if not should_include_file(rel_file, include_exts, exclude_dirs):
                    continue
                if normalize_rel(rel_file) in ignored_files:
                    continue
                count_for_token += 1
                hits_total_estimate += 1
                if len(hits) < max_hits:
                    hits.append(
                        {
                            "token": token,
                            "token_group": group_for_token(token, groups),
                            "file": rel_file,
                            "line": line_no,
                            "snippet": limit_snippet(snippet),
                        }
                    )
            if count_for_token > 0:
                token_hits[token] = token_hits.get(token, 0) + count_for_token

    hits_total = len(hits)
    status = status_from_hits(hits_total=hits_total_estimate, hits=hits if hits else [])
    gate_recommended, gate_reason = build_gate_hint(status)

    top_findings: List[Dict[str, Any]] = []
    for token, count in sorted(token_hits.items(), key=lambda kv: (-kv[1], kv[0]))[:10]:
        examples: List[Dict[str, Any]] = []
        for hit in hits:
            if hit["token"] == token:
                examples.append(
                    {"file": hit["file"], "line": hit["line"], "snippet": hit["snippet"]}
                )
            if len(examples) >= 3:
                break
        top_findings.append({"token": token, "hits": count, "examples": examples})

    report = {
        "repo_root": str(repo_root),
        "generated_at": now_iso(),
        "scanner": scanner,
        "mode": args.mode,
        "inputs": {
            "moves": str(moves_path),
            "scan_report": str(scan_path) if scan_path else None,
            "patch_plan": str(patch_plan_path) if patch_plan_path else None,
        },
        "token_groups": groups,
        "summary": {
            "tokens_total": len(all_tokens),
            "tokens_with_hits": len(token_hits),
            "hits_total": hits_total,
            "total_hits_estimate": hits_total_estimate,
            "status": status,
            "gate_recommended": gate_recommended,
            "gate_reason": gate_reason,
        },
        "top_findings": top_findings,
        "hits": hits,
        "recommended_actions": build_recommended_actions(status),
    }

    report_json = (output_dir / "followup_verify_report.json").resolve()
    report_md = (output_dir / "followup_verify_report.md").resolve()
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_md_report(report_md, report)

    print(f"followup_verify_report_json: {report_json}")
    print(f"followup_verify_report_md: {report_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
