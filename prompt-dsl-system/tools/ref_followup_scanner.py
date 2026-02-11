#!/usr/bin/env python3
"""Static follow-up scanner for move mappings.

Generate candidate reference-fix checklist from src->dst moves using rg/grep.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

DEFAULT_INCLUDE_PATTERNS = [
    "*.java",
    "*.xml",
    "*.yml",
    "*.yaml",
    "*.properties",
    "*.json",
    "*.js",
    "*.ts",
    "*.vue",
    "*.html",
    "*.xhtml",
    "*.jsp",
    "*.sql",
    "*.md",
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


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def limit_snippet(text: str, max_len: int = 200) -> str:
    clean = " ".join(text.strip().split())
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 3] + "..."


def derive_java_fqcn(path_text: str) -> Optional[str]:
    rel = normalize_rel(path_text)
    m = re.search(r"(?:^|/)src/(?:main|test)/java/(.+)\.java$", rel)
    if not m:
        return None
    return m.group(1).replace("/", ".")


def normalize_pattern(pattern: str) -> str:
    p = pattern.strip()
    if not p:
        return p
    if p.startswith("**/") or "/" in p:
        return p
    return f"**/{p}"


def build_tokens(src: str) -> List[str]:
    src_rel = normalize_rel(src)
    tokens: List[str] = []
    basename = Path(src_rel).name
    parent = str(Path(src_rel).parent).replace("\\", "/")

    for token in [basename, src_rel, parent]:
        if token and token != "." and token not in tokens:
            tokens.append(token)

    if src_rel.endswith(".java"):
        fqcn = derive_java_fqcn(src_rel)
        if fqcn and fqcn not in tokens:
            tokens.append(fqcn)
    return tokens


def parse_move_item(item: Dict[str, Any], kind: str) -> Optional[Dict[str, Any]]:
    src = str(item.get("src", "")).strip()
    dst = str(item.get("dst", "")).strip()
    if not src or not dst:
        return None
    notes_raw = item.get("notes")
    notes: List[str] = []
    if isinstance(notes_raw, list):
        notes = [str(x).strip() for x in notes_raw if str(x).strip()]
    return {
        "src": normalize_rel(src),
        "dst": normalize_rel(dst),
        "kind": kind,
        "notes": notes,
    }


def parse_moves_payload(payload: Any) -> List[Dict[str, Any]]:
    moves: List[Dict[str, Any]] = []

    def append_parsed(item: Dict[str, Any], kind: str) -> None:
        parsed = parse_move_item(item, kind)
        if parsed is not None:
            moves.append(parsed)

    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                append_parsed(item, str(item.get("kind", "list")))
    elif isinstance(payload, dict):
        mappings = payload.get("mappings")
        if isinstance(mappings, list):
            default_kind = str(payload.get("strategy", payload.get("kind", "mapping")))
            for item in mappings:
                if isinstance(item, dict):
                    append_parsed(item, default_kind)

        items = payload.get("items")
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    append_parsed(item, str(item.get("kind", item.get("violation_type", "move_report"))))

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
                        append_parsed(item, str(strategy_name))

    dedup: List[Dict[str, Any]] = []
    seen = set()
    for move in moves:
        key = (move["src"], move["dst"], move["kind"])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(move)
    return dedup


def should_include_file(rel_path: str, include_patterns: Sequence[str], exclude_dirs: Sequence[str]) -> bool:
    rel = normalize_rel(rel_path)
    parts = Path(rel).parts
    lowered_dirs = {x.lower() for x in exclude_dirs}
    for part in parts[:-1]:
        if part.lower() in lowered_dirs:
            return False
    base = Path(rel).name
    return any(fnmatch.fnmatch(base, pattern) for pattern in include_patterns)


def build_rg_command(
    token: str,
    include_patterns: Sequence[str],
    exclude_dirs: Sequence[str],
) -> List[str]:
    cmd = ["rg", "--no-config", "--vimgrep", "-F", "-I", "--color", "never", "--hidden", "--no-messages"]
    for p in include_patterns:
        cmd.extend(["-g", normalize_pattern(p)])
    for ex in exclude_dirs:
        ex_name = ex.strip("/").strip()
        if not ex_name:
            continue
        cmd.extend(["-g", f"!**/{ex_name}/**"])
    cmd.extend(["--", token, "."])
    return cmd


def build_grep_command(
    token: str,
    include_patterns: Sequence[str],
    exclude_dirs: Sequence[str],
) -> List[str]:
    cmd = ["grep", "-R", "-H", "-n", "-F"]
    for p in include_patterns:
        cmd.append(f"--include={p}")
    for ex in exclude_dirs:
        ex_name = ex.strip("/").strip()
        if ex_name:
            cmd.append(f"--exclude-dir={ex_name}")
    cmd.extend(["--", token, "."])
    return cmd


def parse_search_output_line(line: str) -> Optional[Tuple[str, int, str]]:
    if not line:
        return None
    if line.startswith("Binary file "):
        return None
    parts = line.split(":", 3)
    if len(parts) >= 4:
        file_part, line_part, _col_part, snippet = parts[0], parts[1], parts[2], parts[3]
    elif len(parts) >= 3:
        file_part, line_part, snippet = parts[0], parts[1], parts[2]
    else:
        return None
    if file_part.isdigit():
        return None
    try:
        line_no = int(line_part)
    except ValueError:
        return None
    rel = normalize_rel(file_part)
    return rel, line_no, snippet


def run_search(
    repo_root: Path,
    scanner: str,
    token: str,
    include_patterns: Sequence[str],
    exclude_dirs: Sequence[str],
) -> List[Tuple[str, int, str]]:
    out: List[Tuple[str, int, str]] = []

    def collect(cmd: List[str]) -> Tuple[List[Tuple[str, int, str]], str]:
        proc = subprocess.run(cmd, cwd=str(repo_root), text=True, capture_output=True)
        rows: List[Tuple[str, int, str]] = []
        for line in (proc.stdout.splitlines() if proc.stdout else []):
            parsed = parse_search_output_line(line)
            if parsed is None:
                continue
            rows.append(parsed)
        return rows, proc.stdout or ""

    if scanner == "rg":
        rg_rows, rg_stdout = collect(build_rg_command(token, include_patterns, exclude_dirs))
        out.extend(rg_rows)
        # Fallback: local rg may omit filename in some configs.
        if not out and rg_stdout.strip():
            grep_rows, _ = collect(build_grep_command(token, include_patterns, exclude_dirs))
            out.extend(grep_rows)
    elif scanner == "grep":
        grep_rows, _ = collect(build_grep_command(token, include_patterns, exclude_dirs))
        out.extend(grep_rows)
    else:
        return []

    return out


def classify_extensions(hits: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    by_ext: Dict[str, int] = {}
    for hit in hits:
        file_path = str(hit.get("file", ""))
        ext = Path(file_path).suffix.lower() or "(no-ext)"
        by_ext[ext] = by_ext.get(ext, 0) + 1
    return dict(sorted(by_ext.items(), key=lambda kv: (-kv[1], kv[0])))


def scoped_dirs(src: str, dst: str) -> List[str]:
    candidates = {
        str(Path(src).parent).replace("\\", "/"),
        str(Path(dst).parent).replace("\\", "/"),
    }
    cleaned = [c for c in sorted(candidates) if c and c != "."]
    return cleaned if cleaned else ["."]


def build_recommendations(move: Dict[str, Any], hits: Sequence[Dict[str, Any]]) -> List[Dict[str, str]]:
    src = move["src"]
    dst = move["dst"]
    recs: List[Dict[str, str]] = []

    if hits:
        recs.append({"type": "manual_review", "reason": "static hits found; confirm each reference before edit"})
    else:
        recs.append({"type": "manual_review", "reason": "no static hits found in scanned file types"})

    if src != dst:
        recs.append({"type": "candidate_replace", "from": src, "to": dst, "confidence": "low"})

    src_fqcn = derive_java_fqcn(src)
    dst_fqcn = derive_java_fqcn(dst)
    if src_fqcn and dst_fqcn and src_fqcn != dst_fqcn:
        recs.append(
            {"type": "candidate_replace", "from": src_fqcn, "to": dst_fqcn, "confidence": "medium"}
        )
    return recs


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Scan follow-up references for move mappings")
    p.add_argument("--repo-root", required=True)
    p.add_argument("--moves", required=True, help="JSON file: conflict_plan.json or move_report.json or mapping")
    p.add_argument("--output-dir", default="prompt-dsl-system/tools")
    p.add_argument("--max-hits-per-move", type=int, default=50)
    p.add_argument("--use-rg", default="true")
    p.add_argument("--include", action="append", default=[])
    p.add_argument("--exclude", action="append", default=[])
    p.add_argument("--mode", choices=["plan", "apply"], default="plan")
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

    include_patterns = list(dict.fromkeys(DEFAULT_INCLUDE_PATTERNS + [x for x in args.include if str(x).strip()]))
    exclude_dirs = list(dict.fromkeys(DEFAULT_EXCLUDE_DIRS + [x for x in args.exclude if str(x).strip()]))
    max_hits = max(1, int(args.max_hits_per_move))

    use_rg = parse_bool(args.use_rg, default=True)
    scanner = "none"
    if use_rg and shutil.which("rg"):
        scanner = "rg"
    elif shutil.which("grep"):
        scanner = "grep"

    try:
        payload = load_json(moves_path)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"failed to parse moves JSON: {moves_path}: {exc}", file=sys.stderr)
        return 2

    moves = parse_moves_payload(payload)
    report_moves: List[Dict[str, Any]] = []

    for move in moves:
        src = move["src"]
        dst = move["dst"]
        tokens = build_tokens(src)
        hits: List[Dict[str, Any]] = []
        truncated = False
        seen_hits = set()

        for token in tokens:
            if not token:
                continue
            scan_rows = run_search(repo_root, scanner, token, include_patterns, exclude_dirs)
            for file_rel, line_no, snippet in scan_rows:
                if not should_include_file(file_rel, include_patterns, exclude_dirs):
                    continue
                key = (file_rel, line_no, token)
                if key in seen_hits:
                    continue
                seen_hits.add(key)
                if len(hits) >= max_hits:
                    truncated = True
                    break
                hits.append(
                    {
                        "file": file_rel,
                        "line": line_no,
                        "snippet": limit_snippet(snippet, max_len=200),
                        "matched_token": token,
                    }
                )
            if truncated:
                break

        report_moves.append(
            {
                "src": src,
                "dst": dst,
                "kind": move.get("kind", "move"),
                "notes": move.get("notes", []),
                "tokens": tokens,
                "hits": hits,
                "truncated": truncated,
                "recommendations": build_recommendations(move, hits),
            }
        )

    report = {
        "repo_root": str(repo_root),
        "moves_source": str(moves_path),
        "generated_at": now_iso(),
        "mode": args.mode,
        "scanner": scanner,
        "use_rg_requested": use_rg,
        "include_patterns": include_patterns,
        "exclude_dirs": exclude_dirs,
        "max_hits_per_move": max_hits,
        "moves": report_moves,
    }

    report_path = output_dir / "followup_scan_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    checklist_path = output_dir / "followup_checklist.md"
    lines: List[str] = []
    lines.append("# followup_checklist")
    lines.append("")
    lines.append(f"- generated_at: {report['generated_at']}")
    lines.append(f"- scanner: {scanner}")
    lines.append(f"- moves_source: {moves_path}")
    lines.append(f"- move_count: {len(report_moves)}")
    lines.append("- note: 静态扫描结果仅为候选，请人工确认后再修改。")
    lines.append("")

    if not report_moves:
        lines.append("## Result")
        lines.append("- no moves parsed from input json")
    else:
        for idx, move in enumerate(report_moves, start=1):
            src = move["src"]
            dst = move["dst"]
            tokens = move["tokens"]
            hits = move["hits"]
            by_ext = classify_extensions(hits)
            scopes = scoped_dirs(src, dst)

            lines.append(f"## Move {idx}: `{src}` -> `{dst}`")
            lines.append(f"- kind: {move.get('kind', 'move')}")
            lines.append(f"- token_count: {len(tokens)}")
            lines.append(f"- hit_count: {len(hits)}")
            lines.append(f"- truncated: {str(bool(move.get('truncated'))).lower()}")
            lines.append("- tokens:")
            if tokens:
                for token in tokens:
                    lines.append(f"  - `{token}`")
            else:
                lines.append("  - (none)")

            lines.append("- possible reference types (by extension):")
            if by_ext:
                for ext, count in by_ext.items():
                    lines.append(f"  - `{ext}`: {count}")
            else:
                lines.append("  - no hits")

            lines.append("- quick scan commands:")
            scope_str = " ".join(shlex.quote(x) for x in scopes) if scopes else "."
            for token in tokens[:4]:
                quoted = shlex.quote(token)
                if scanner == "rg":
                    lines.append(f"  - `rg -n -F -- {quoted} {scope_str}`")
                elif scanner == "grep":
                    lines.append(f"  - `grep -R -n -F -- {quoted} {scope_str}`")
                else:
                    lines.append(f"  - `(scanner unavailable) token={token}`")

            lines.append("- top hits (max 10):")
            if hits:
                for hit in hits[:10]:
                    lines.append(
                        f"  - `{hit['file']}:{hit['line']}` token=`{hit['matched_token']}` :: {hit['snippet']}"
                    )
                if len(hits) > 10:
                    lines.append(
                        f"  - ... {len(hits) - 10} more hits (see `followup_scan_report.json`)"
                    )
            else:
                lines.append("  - no hits")

            lines.append("- recommendations:")
            recs = move.get("recommendations", [])
            if isinstance(recs, list) and recs:
                for rec in recs:
                    if rec.get("type") == "candidate_replace":
                        lines.append(
                            f"  - candidate_replace ({rec.get('confidence','low')}): "
                            f"`{rec.get('from','')}` -> `{rec.get('to','')}`"
                        )
                    else:
                        lines.append(f"  - {rec.get('type','manual_review')}: {rec.get('reason','')}")
            else:
                lines.append("  - manual_review: verify references before any edit")
            lines.append("")

    checklist_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"followup_scan_report: {report_path}")
    print(f"followup_checklist: {checklist_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
