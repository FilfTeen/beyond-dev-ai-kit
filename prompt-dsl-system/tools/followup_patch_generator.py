#!/usr/bin/env python3
"""Generate/apply conservative follow-up replacement patches from scan report."""

from __future__ import annotations

import argparse
import difflib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

DEFAULT_SAFE_EXTS = [
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
    ".md",
]

DEFAULT_EXCLUDE_PATHS = [
    ".git/",
    "/target/",
    ".idea/",
    ".vscode/",
    "node_modules/",
    "/dist/",
    "/build/",
    "/out/",
    "/logs/",
]

FRONTEND_EXTS = {".html", ".xhtml", ".jsp", ".js", ".ts", ".vue"}
JAVA_XML_EXTS = {".java", ".xml"}
BOUNDARY_CHARS = set(" \t\r\n\"'`()[]{}<>,;:=|")
CONFIDENCE_RANK = {"low": 1, "medium": 2, "high": 3}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_rel(path_text: str) -> str:
    text = str(path_text).replace("\\", "/").strip()
    while text.startswith("./"):
        text = text[2:]
    return text


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


def safe_read_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


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
        raise ValueError(f"path must be under repo root: {path_arg}") from exc
    if require_exists and not p.exists():
        raise ValueError(f"path does not exist: {path_arg}")
    return p


def derive_java_fqcn(path_text: str) -> Optional[str]:
    rel = normalize_rel(path_text)
    marker = "src/main/java/"
    marker2 = "src/test/java/"
    idx = rel.find(marker)
    if idx < 0:
        idx = rel.find(marker2)
        if idx < 0:
            return None
        tail = rel[idx + len(marker2) :]
    else:
        tail = rel[idx + len(marker) :]
    if not tail.endswith(".java"):
        return None
    return tail[:-5].replace("/", ".")


def normalize_ext(ext: str) -> str:
    text = str(ext).strip().lower()
    if not text:
        return ""
    if not text.startswith("."):
        text = "." + text
    return text


def normalize_exclude_path(path: str) -> str:
    text = normalize_rel(path).lower()
    if not text:
        return ""
    if not text.startswith("/"):
        text = "/" + text
    if not text.endswith("/"):
        text = text + "/"
    return text


def is_path_excluded(rel_path: str, excludes: Sequence[str]) -> bool:
    norm = "/" + normalize_rel(rel_path).lower().strip("/") + "/"
    return any(ex in norm for ex in excludes)


def is_binary_file(path: Path) -> bool:
    try:
        sample = path.read_bytes()[:4096]
    except OSError:
        return True
    return b"\x00" in sample


def read_text_with_fallback(path: Path) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    try:
        raw = path.read_bytes()
    except OSError:
        return None, None, None
    for enc in ("utf-8", "latin-1"):
        try:
            text = raw.decode(enc)
            newline = "\n"
            if "\r\n" in text:
                newline = "\r\n"
            return text, enc, newline
        except UnicodeDecodeError:
            continue
    return None, None, None


def replace_with_boundaries(text: str, old: str, new: str, limit: int) -> Tuple[str, int]:
    if not old or limit <= 0:
        return text, 0
    result: List[str] = []
    idx = 0
    replaced = 0
    n = len(old)
    while idx < len(text):
        pos = text.find(old, idx)
        if pos < 0 or replaced >= limit:
            result.append(text[idx:])
            break
        end = pos + n
        before_ok = pos == 0 or text[pos - 1] in BOUNDARY_CHARS
        after_ok = end == len(text) or text[end] in BOUNDARY_CHARS
        if before_ok and after_ok:
            result.append(text[idx:pos])
            result.append(new)
            idx = end
            replaced += 1
        else:
            result.append(text[idx : pos + 1])
            idx = pos + 1
    else:
        result.append("")
    return "".join(result), replaced


def replace_fqcn_in_context(text: str, old: str, new: str, limit: int) -> Tuple[str, int]:
    if not old or limit <= 0:
        return text, 0
    keywords = ("import ", "class=", "mapper=", "resultType=", "parameterType=", "type=")
    lines = text.splitlines(keepends=True)
    out: List[str] = []
    replaced = 0
    for line in lines:
        if replaced >= limit or old not in line or not any(k in line for k in keywords):
            out.append(line)
            continue
        room = limit - replaced
        c = line.count(old)
        use = min(room, c)
        if use > 0:
            line = line.replace(old, new, use)
            replaced += use
        out.append(line)
    return "".join(out), replaced


def replace_frontend_context(text: str, old: str, new: str, limit: int) -> Tuple[str, int]:
    if not old or limit <= 0:
        return text, 0
    lines = text.splitlines(keepends=True)
    out: List[str] = []
    replaced = 0

    for line in lines:
        if replaced >= limit or old not in line:
            out.append(line)
            continue

        updated = line
        patterns = [
            (" src/href ", ['src="', "src='", 'href="', "href='"]),
            (" require ", ['require("', "require('"]),
            (" import ", ['import "', "import '", 'from "', "from '"]),
        ]

        for _label, markers in patterns:
            if replaced >= limit:
                break
            if not any(m in updated for m in markers):
                continue
            room = limit - replaced
            c = updated.count(old)
            if c <= 0:
                continue
            use = min(room, c)
            updated = updated.replace(old, new, use)
            replaced += use

        out.append(updated)

    return "".join(out), replaced


def parse_moves(scan_report: Dict[str, Any]) -> List[Dict[str, Any]]:
    moves_raw = scan_report.get("moves")
    if not isinstance(moves_raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in moves_raw:
        if not isinstance(item, dict):
            continue
        src = str(item.get("src", "")).strip()
        dst = str(item.get("dst", "")).strip()
        if not src or not dst:
            continue
        hits_raw = item.get("hits")
        hits = hits_raw if isinstance(hits_raw, list) else []
        out.append(
            {
                "src": normalize_rel(src),
                "dst": normalize_rel(dst),
                "hits": hits,
            }
        )
    return out


def move_old_tail(old_dir: str) -> str:
    parts = [p for p in normalize_rel(old_dir).split("/") if p]
    if not parts:
        return ""
    if len(parts) <= 3:
        return "/".join(parts)
    return "/".join(parts[-3:])


def move_new_tail(new_dir: str) -> str:
    return move_old_tail(new_dir)


def candidate_key(c: Dict[str, Any]) -> Tuple[str, str, str, str]:
    return (
        str(c.get("file", "")),
        str(c.get("rule", "")),
        str(c.get("from", "")),
        str(c.get("to", "")),
    )


def build_candidates(
    moves: Sequence[Dict[str, Any]],
    include_exts: Sequence[str],
    exclude_paths: Sequence[str],
    threshold: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    candidates: List[Dict[str, Any]] = []
    skipped: List[Dict[str, str]] = []
    threshold_rank = CONFIDENCE_RANK.get(threshold, 3)

    for idx, move in enumerate(moves, start=1):
        src = move["src"]
        dst = move["dst"]
        old_dir = str(Path(src).parent).replace("\\", "/")
        new_dir = str(Path(dst).parent).replace("\\", "/")
        old_tail = move_old_tail(old_dir)
        new_tail = move_new_tail(new_dir)
        old_fqcn = derive_java_fqcn(src)
        new_fqcn = derive_java_fqcn(dst)

        hits = move.get("hits", [])
        if not isinstance(hits, list):
            continue
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            rel_file = normalize_rel(str(hit.get("file", "")).strip())
            if not rel_file:
                continue
            ext = Path(rel_file).suffix.lower()
            token = str(hit.get("matched_token", "")).strip()
            snippet = str(hit.get("snippet", ""))

            if ext and ext not in include_exts:
                skipped.append({"file": rel_file, "reason": f"ext filtered: {ext}"})
                continue
            if is_path_excluded(rel_file, exclude_paths):
                skipped.append({"file": rel_file, "reason": "path excluded"})
                continue

            # Rule A: full old path -> new path
            if token == src:
                cand = {
                    "move_index": idx,
                    "file": rel_file,
                    "rule": "A_full_path",
                    "from": src,
                    "to": dst,
                    "confidence": "high",
                    "line_hint": hit.get("line"),
                    "reason": "token matched full old path",
                }
                if CONFIDENCE_RANK[cand["confidence"]] >= threshold_rank:
                    candidates.append(cand)

            # Rule B: frontend static path context
            if ext in FRONTEND_EXTS and ("src=" in snippet or "href=" in snippet or "require(" in snippet or "import " in snippet):
                if token == old_dir or old_dir in snippet:
                    cand = {
                        "move_index": idx,
                        "file": rel_file,
                        "rule": "B_frontend_old_dir",
                        "from": old_dir,
                        "to": new_dir,
                        "confidence": "high",
                        "line_hint": hit.get("line"),
                        "reason": "frontend context with old directory",
                    }
                    if CONFIDENCE_RANK[cand["confidence"]] >= threshold_rank:
                        candidates.append(cand)
                elif old_tail and old_tail in snippet and new_tail:
                    cand = {
                        "move_index": idx,
                        "file": rel_file,
                        "rule": "B_frontend_tail_dir",
                        "from": old_tail,
                        "to": new_tail,
                        "confidence": "high",
                        "line_hint": hit.get("line"),
                        "reason": "frontend context with tail directory",
                    }
                    if CONFIDENCE_RANK[cand["confidence"]] >= threshold_rank:
                        candidates.append(cand)

            # Rule C: Java FQCN import/class/mapper context
            if old_fqcn and new_fqcn and ext in JAVA_XML_EXTS and (
                token == old_fqcn or old_fqcn in snippet
            ):
                if any(k in snippet for k in ("import ", "class=", "mapper=", "resultType=", "parameterType=", "type=")):
                    cand = {
                        "move_index": idx,
                        "file": rel_file,
                        "rule": "C_java_fqcn",
                        "from": old_fqcn,
                        "to": new_fqcn,
                        "confidence": "high",
                        "line_hint": hit.get("line"),
                        "reason": "java/xml context with fqcn",
                    }
                    if CONFIDENCE_RANK[cand["confidence"]] >= threshold_rank:
                        candidates.append(cand)

    dedup: List[Dict[str, Any]] = []
    seen = set()
    for cand in candidates:
        key = candidate_key(cand)
        if key in seen:
            continue
        seen.add(key)
        dedup.append(cand)
    return dedup, skipped


def load_ack_token_from_json(path: Path) -> Optional[str]:
    data = safe_read_json(path)
    token = data.get("token")
    if isinstance(token, str) and token.strip():
        return token.strip()
    if isinstance(token, dict):
        value = token.get("value")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def run_risk_gate(
    repo_root: Path,
    output_dir: Path,
    guard_report: Path,
    loop_report: Path,
    scan_report: Path,
    patch_plan: Path,
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
        "--scan-report",
        to_repo_relative(scan_report, repo_root),
        "--patch-plan",
        to_repo_relative(patch_plan, repo_root),
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


def write_plan_md(path: Path, plan: Dict[str, Any]) -> None:
    lines: List[str] = []
    lines.append("# followup_patch_plan")
    lines.append("")
    lines.append(f"- generated_at: {plan.get('generated_at')}")
    lines.append(f"- mode: {plan.get('mode')}")
    lines.append(f"- scan_report: {plan.get('scan_report')}")
    lines.append(f"- confidence_threshold: {plan.get('confidence_threshold')}")
    lines.append(f"- max_changes: {plan.get('max_changes')}")
    lines.append(f"- total_candidates: {plan.get('total_candidates')}")
    lines.append(f"- selected_candidates: {plan.get('selected_candidates')}")
    lines.append(f"- total_replacements: {plan.get('total_replacements')}")
    lines.append(f"- files_changed: {plan.get('files_changed')}")
    lines.append(f"- truncated: {str(bool(plan.get('truncated'))).lower()}")
    lines.append("")
    lines.append("## Rules")
    lines.append("- A_full_path: 完整旧路径字符串替换（高置信度）。")
    lines.append("- B_frontend_old_dir/B_frontend_tail_dir: 前端静态资源路径上下文替换（高置信度）。")
    lines.append("- C_java_fqcn: Java/XML import/class/mapper 等上下文 FQCN 替换（高置信度）。")
    lines.append("- 禁止：basename-only、SQL 语义级、二进制文件。")
    lines.append("")
    lines.append("## File Changes")
    files = plan.get("files")
    if not isinstance(files, list) or not files:
        lines.append("- no patchable high-confidence replacements")
    else:
        for item in files:
            if not isinstance(item, dict):
                continue
            lines.append(f"- `{item.get('file')}` (replacements={item.get('total_replacements',0)})")
            reps = item.get("replacements")
            if isinstance(reps, list):
                for rep in reps:
                    lines.append(
                        f"  - {rep.get('rule')}: `{rep.get('from')}` -> `{rep.get('to')}` "
                        f"(count={rep.get('count',0)}, confidence={rep.get('confidence')})"
                    )
    lines.append("")
    if plan.get("truncated"):
        lines.append("## Truncation")
        lines.append("- changes exceeded max_changes; plan truncated, manual intervention required.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_apply_log(path: Path, payload: Dict[str, Any]) -> None:
    lines: List[str] = []
    lines.append("# followup_patch_apply_log")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- result: {payload.get('result')}")
    lines.append(f"- message: {payload.get('message')}")
    lines.append("")
    lines.append("## File Apply Results")
    items = payload.get("items")
    if isinstance(items, list) and items:
        for idx, item in enumerate(items, start=1):
            lines.append(f"{idx}. `{item.get('file')}`")
            lines.append(f"   - status: {item.get('status')}")
            lines.append(f"   - detail: {item.get('detail')}")
    else:
        lines.append("- no files applied")
    lines.append("")
    lines.append("## Next")
    lines.append("- ./prompt-dsl-system/tools/run.sh debug-guard -r . -m <MODULE_PATH>")
    lines.append("- ./prompt-dsl-system/tools/run.sh validate -r .")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate/apply conservative follow-up replacement patch")
    p.add_argument("--repo-root", required=True)
    p.add_argument("--scan-report", required=True)
    p.add_argument("--output-dir", default="prompt-dsl-system/tools")
    p.add_argument("--mode", choices=["plan", "apply"], default="plan")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--dry-run", default="true")
    p.add_argument("--max-changes", default="100")
    p.add_argument("--confidence-threshold", choices=["low", "medium", "high"], default="high")
    p.add_argument("--include-ext", action="append", default=[])
    p.add_argument("--exclude-path", action="append", default=[])
    p.add_argument("--ack")
    p.add_argument("--ack-file")
    p.add_argument("--ack-latest", action="store_true")
    p.add_argument("--risk-threshold", default="HIGH")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        print(f"Invalid repo root: {repo_root}", file=sys.stderr)
        return 2

    try:
        scan_report_path = resolve_under_repo(repo_root, args.scan_report, require_exists=True)
        output_dir = resolve_under_repo(repo_root, args.output_dir, require_exists=False)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    output_dir.mkdir(parents=True, exist_ok=True)

    max_changes = int(args.max_changes) if str(args.max_changes).strip().isdigit() else 100
    max_changes = max(1, max_changes)

    include_exts = [normalize_ext(x) for x in DEFAULT_SAFE_EXTS + list(args.include_ext or [])]
    include_exts = sorted({x for x in include_exts if x})
    exclude_paths = [normalize_exclude_path(x) for x in DEFAULT_EXCLUDE_PATHS + list(args.exclude_path or [])]
    exclude_paths = sorted({x for x in exclude_paths if x})

    scan_report = safe_read_json(scan_report_path)
    if not scan_report:
        print(f"failed to parse scan report: {scan_report_path}", file=sys.stderr)
        return 2

    moves = parse_moves(scan_report)
    moves_source_hint_raw = scan_report.get("moves_source")
    moves_source_hint = None
    if isinstance(moves_source_hint_raw, str) and moves_source_hint_raw.strip():
        try:
            moves_source_path = resolve_under_repo(repo_root, moves_source_hint_raw, require_exists=False)
            moves_source_hint = to_repo_relative(moves_source_path, repo_root)
        except ValueError:
            moves_source_hint = None
    candidates, skipped_hits = build_candidates(
        moves=moves,
        include_exts=include_exts,
        exclude_paths=exclude_paths,
        threshold=args.confidence_threshold,
    )

    by_file: Dict[str, List[Dict[str, Any]]] = {}
    for c in candidates:
        by_file.setdefault(c["file"], []).append(c)

    file_plans: List[Dict[str, Any]] = []
    diffs: List[str] = []
    total_replacements = 0
    files_changed = 0
    truncated = False
    remaining = max_changes
    runtime_changes: List[Dict[str, Any]] = []

    for rel_file in sorted(by_file.keys()):
        abs_file = (repo_root / rel_file).resolve()
        if is_path_excluded(rel_file, exclude_paths):
            continue
        ext = abs_file.suffix.lower()
        if ext and ext not in include_exts:
            continue
        if not abs_file.exists() or not abs_file.is_file():
            file_plans.append({"file": rel_file, "status": "skipped", "reason": "file missing"})
            continue
        if is_binary_file(abs_file):
            file_plans.append({"file": rel_file, "status": "skipped", "reason": "binary file"})
            continue

        text, encoding, _newline = read_text_with_fallback(abs_file)
        if text is None:
            file_plans.append({"file": rel_file, "status": "skipped", "reason": "decode failed"})
            continue
        original = text
        current = text
        replacements: List[Dict[str, Any]] = []

        ordered = sorted(
            by_file[rel_file],
            key=lambda x: {"A_full_path": 0, "C_java_fqcn": 1, "B_frontend_old_dir": 2, "B_frontend_tail_dir": 3}.get(
                str(x.get("rule")), 9
            ),
        )

        for c in ordered:
            if remaining <= 0:
                truncated = True
                break
            old = str(c.get("from", ""))
            new = str(c.get("to", ""))
            rule = str(c.get("rule", ""))
            count = 0

            if rule == "A_full_path":
                current, count = replace_with_boundaries(current, old, new, remaining)
            elif rule == "C_java_fqcn":
                current, count = replace_fqcn_in_context(current, old, new, remaining)
            elif rule in {"B_frontend_old_dir", "B_frontend_tail_dir"}:
                current, count = replace_frontend_context(current, old, new, remaining)
            else:
                continue

            if count > 0:
                remaining -= count
                total_replacements += count
                replacements.append(
                    {
                        "rule": rule,
                        "from": old,
                        "to": new,
                        "count": count,
                        "confidence": c.get("confidence", "high"),
                        "reason": c.get("reason", ""),
                    }
                )
            if remaining <= 0:
                truncated = True
                break

        if current != original:
            files_changed += 1
            diff_lines = list(
                difflib.unified_diff(
                    original.splitlines(keepends=True),
                    current.splitlines(keepends=True),
                    fromfile=rel_file,
                    tofile=rel_file,
                    lineterm="",
                )
            )
            if diff_lines:
                diffs.append("\n".join(diff_lines) + "\n")
            file_plans.append(
                {
                    "file": rel_file,
                    "status": "changed",
                    "encoding": encoding,
                    "total_replacements": sum(int(x["count"]) for x in replacements),
                    "replacements": replacements,
                }
            )
            runtime_changes.append(
                {
                    "file": rel_file,
                    "encoding": encoding,
                    "original": original,
                    "updated": current,
                    "replacements": replacements,
                }
            )
        else:
            file_plans.append(
                {
                    "file": rel_file,
                    "status": "no_change",
                    "encoding": encoding,
                    "total_replacements": 0,
                    "replacements": [],
                }
            )

    plan = {
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "scan_report": to_repo_relative(scan_report_path, repo_root),
        "mode": args.mode,
        "confidence_threshold": args.confidence_threshold,
        "max_changes": max_changes,
        "include_exts": include_exts,
        "exclude_paths": exclude_paths,
        "total_moves": len(moves),
        "total_candidates": len(candidates),
        "selected_candidates": len(candidates),
        "files_changed": files_changed,
        "total_replacements": total_replacements,
        "truncated": truncated,
        "files": file_plans,
        "skipped_hits": skipped_hits[:200],
    }

    plan_json = (output_dir / "followup_patch_plan.json").resolve()
    plan_md = (output_dir / "followup_patch_plan.md").resolve()
    patch_diff = (output_dir / "followup_patch.diff").resolve()
    apply_log = (output_dir / "followup_patch_apply_log.md").resolve()

    plan_json.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    write_plan_md(plan_md, plan)
    patch_diff.write_text("".join(diffs), encoding="utf-8")

    print(f"followup_patch_plan_json: {to_repo_relative(plan_json, repo_root)}")
    print(f"followup_patch_plan_md: {to_repo_relative(plan_md, repo_root)}")
    print(f"followup_patch_diff: {to_repo_relative(patch_diff, repo_root)}")

    if args.mode == "plan":
        return 0

    dry_run = parse_bool(args.dry_run, default=True)
    if not args.yes or dry_run:
        print("apply requires --yes and --dry-run false; patch plan generated only.", file=sys.stderr)
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
        ack = load_ack_token_from_json(ack_file_path)

    synthetic_loop = (output_dir / "followup_patch_loop_high.json").resolve()
    synthetic_loop.write_text(
        json.dumps(
            {
                "generated_at": now_iso(),
                "level": "HIGH",
                "triggers": [{"id": "FOLLOWUP_PATCH_APPLY", "severity": "HIGH"}],
                "recommendation": ["review followup patch plan before apply"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    guard_report = (output_dir / "guard_report.json").resolve()
    if not guard_report.exists():
        guard_report = (repo_root / "prompt-dsl-system" / "tools" / "guard_report.json").resolve()
    gate_rc = run_risk_gate(
        repo_root=repo_root,
        output_dir=output_dir,
        guard_report=guard_report,
        loop_report=synthetic_loop,
        scan_report=scan_report_path,
        patch_plan=plan_json,
        threshold=str(args.risk_threshold).upper(),
        ack=ack,
    )
    if gate_rc != 0:
        print("risk gate blocked followup patch apply", file=sys.stderr)
        print(
            "Use ACK token and rerun: ./prompt-dsl-system/tools/run.sh apply-followup-fixes -r . "
            "--scan-report <SCAN_REPORT> --mode apply --yes --dry-run false --ack-latest",
            file=sys.stderr,
        )
        return gate_rc

    apply_items: List[Dict[str, str]] = []
    ok = True
    message = "applied"
    for item in runtime_changes:
        rel_file = str(item["file"])
        abs_file = (repo_root / rel_file).resolve()
        current_text, enc, _nl = read_text_with_fallback(abs_file)
        if current_text is None:
            ok = False
            message = "apply failed"
            apply_items.append({"file": rel_file, "status": "failed", "detail": "decode failed before write"})
            break

        # Re-check key replacement anchors.
        anchors_ok = True
        for rep in item.get("replacements", []):
            frm = str(rep.get("from", ""))
            cnt = int(rep.get("count", 0))
            if cnt > 0 and frm and frm not in current_text:
                anchors_ok = False
                apply_items.append(
                    {
                        "file": rel_file,
                        "status": "failed",
                        "detail": f"anchor missing before apply: {frm}",
                    }
                )
                break
        if not anchors_ok:
            ok = False
            message = "apply failed"
            break

        try:
            abs_file.write_text(str(item["updated"]), encoding=enc or "utf-8")
        except OSError as exc:
            ok = False
            message = "apply failed"
            apply_items.append({"file": rel_file, "status": "failed", "detail": f"write error: {exc}"})
            break
        apply_items.append({"file": rel_file, "status": "applied", "detail": "ok"})

    if ok:
        message = "applied"
    payload = {
        "generated_at": now_iso(),
        "result": "success" if ok else "failed",
        "message": message,
        "items": apply_items,
    }
    write_apply_log(apply_log, payload)
    print(f"followup_patch_apply_log: {to_repo_relative(apply_log, repo_root)}")
    verify_moves_arg = moves_source_hint or "<MOVES_JSON>"
    print(
        "next: ./prompt-dsl-system/tools/run.sh verify-followup-fixes -r . "
        f"--moves {verify_moves_arg} "
        f"--scan-report {to_repo_relative(scan_report_path, repo_root)} "
        f"--patch-plan {to_repo_relative(plan_json, repo_root)}"
    )
    print("next: ./prompt-dsl-system/tools/run.sh debug-guard -r . -m <MODULE_PATH>")
    print("next: ./prompt-dsl-system/tools/run.sh validate -r .")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
