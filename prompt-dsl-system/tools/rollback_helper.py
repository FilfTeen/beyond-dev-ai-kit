#!/usr/bin/env python3
"""Generate rollback plan and move plan from guard report.

Safe by default: only generates plans/reports/scripts; no file moves unless explicitly requested.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path.resolve()).replace("\\", "/")


def normalize_rel(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


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


def detect_vcs(repo_root: Path, report: Dict[str, Any]) -> str:
    vcs = report.get("vcs")
    if isinstance(vcs, str) and vcs in {"git", "svn", "none", "synthetic"}:
        if vcs == "synthetic":
            if (repo_root / ".git").exists():
                return "git"
            if (repo_root / ".svn").exists():
                return "svn"
            return "none"
        return vcs

    if (repo_root / ".git").exists():
        return "git"
    if (repo_root / ".svn").exists():
        return "svn"
    return "none"


def load_guard_report(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"Guard report not found: {path}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"Guard report parse failed: {exc}")


def resolve_under_repo(path_arg: str, repo_root: Path, require_exists: bool) -> Path:
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


def resolve_module_path(
    cli_module_path: Optional[str], report: Dict[str, Any], repo_root: Path
) -> Tuple[Optional[Path], Optional[str], str, List[str]]:
    warnings: List[str] = []

    if cli_module_path:
        candidate = resolve_under_repo(cli_module_path, repo_root, require_exists=False)
        return candidate, to_repo_relative(candidate, repo_root), "cli", warnings

    report_rel = report.get("module_path_normalized")
    if isinstance(report_rel, str) and report_rel.strip():
        rel_norm = normalize_rel(report_rel)
        candidate = (repo_root / rel_norm).resolve()
        return candidate, rel_norm, "report", warnings

    report_abs = report.get("module_path")
    if isinstance(report_abs, str) and report_abs.strip():
        try:
            candidate = resolve_under_repo(report_abs, repo_root, require_exists=False)
            return candidate, to_repo_relative(candidate, repo_root), "report", warnings
        except ValueError:
            warnings.append(f"Ignored report module_path outside repo: {report_abs}")

    return None, None, "none", warnings


def classify_violation(item: Dict[str, Any]) -> str:
    vtype = item.get("type")
    if isinstance(vtype, str) and vtype in {"forbidden", "outside_module", "missing_module_path"}:
        return vtype

    rule = str(item.get("rule", "")).strip()
    if rule == "forbidden_path_patterns":
        return "forbidden"
    if rule == "out_of_allowed_scope":
        return "outside_module"
    if rule == "module_path_required":
        return "missing_module_path"
    return "outside_module"


def collect_targets(report: Dict[str, Any], only_violations: bool) -> Tuple[List[str], Dict[str, Dict[str, Any]]]:
    violations_raw = report.get("violations")
    violations = violations_raw if isinstance(violations_raw, list) else []

    violation_by_file: Dict[str, Dict[str, Any]] = {}
    for v in violations:
        if not isinstance(v, dict):
            continue
        file_path = v.get("file")
        if not isinstance(file_path, str) or not file_path.strip():
            continue
        rel = normalize_rel(file_path)
        if rel not in violation_by_file:
            v = dict(v)
            v["type"] = classify_violation(v)
            violation_by_file[rel] = v

    if only_violations:
        return sorted(violation_by_file.keys()), violation_by_file

    changed_raw = report.get("changed_files")
    changed = changed_raw if isinstance(changed_raw, list) else []
    files: List[str] = []
    for item in changed:
        if isinstance(item, str) and item.strip():
            files.append(normalize_rel(item))

    if not files:
        files = sorted(violation_by_file.keys())

    dedup: List[str] = []
    seen = set()
    for f in files:
        if f not in seen:
            seen.add(f)
            dedup.append(f)

    return dedup, violation_by_file


def detect_segment_suffix(src: str) -> Optional[Tuple[str, str]]:
    normalized = normalize_rel(src)
    strong_segments = [
        "src/main/java/",
        "src/main/resources/",
        "src/main/webapp/",
        "src/test/java/",
        "src/test/resources/",
    ]

    for seg in strong_segments:
        idx = normalized.find(seg)
        if idx >= 0:
            suffix = normalized[idx + len(seg) :]
            if not suffix:
                suffix = Path(normalized).name
            return seg, suffix

    if normalized.startswith("sql/"):
        suffix = normalized[len("sql/") :]
        if not suffix:
            suffix = Path(normalized).name
        return "sql/", suffix
    if "/sql/" in normalized:
        idx = normalized.find("/sql/")
        suffix = normalized[idx + len("/sql/") :]
        if not suffix:
            suffix = Path(normalized).name
        return "sql/", suffix

    if normalized.startswith("pages/"):
        suffix = normalized[len("pages/") :]
        if not suffix:
            suffix = Path(normalized).name
        return "pages/", suffix
    if "/pages/" in normalized:
        idx = normalized.find("/pages/")
        suffix = normalized[idx + len("/pages/") :]
        if not suffix:
            suffix = Path(normalized).name
        return "pages/", suffix

    return None


def sanitize_path_token(src: str) -> Tuple[str, bool]:
    s = normalize_rel(src)
    while s.startswith("../"):
        s = s[3:]
    token = s.replace("/", "__")

    if len(token) <= 160:
        return token, False

    ext = ""
    base_name = Path(s).name
    if "." in base_name and not base_name.startswith("."):
        ext = "." + base_name.split(".")[-1]

    hash8 = hashlib.sha1(s.encode("utf-8")).hexdigest()[:8]
    reserve = len(ext) + 9
    keep = max(16, 160 - reserve)
    return f"{token[:keep]}_{hash8}{ext}", True


def build_move_destination(
    src: str,
    module_rel: str,
    prefer_preserve_structure: bool,
) -> Dict[str, Any]:
    src_norm = normalize_rel(src)

    if prefer_preserve_structure:
        seg = detect_segment_suffix(src_norm)
        if seg is not None:
            segment, suffix = seg
            dst = f"{module_rel.rstrip('/')}/{segment}{suffix}".replace("//", "/")
            return {
                "dst": normalize_rel(dst),
                "strategy": "preserve",
                "token_truncated": False,
                "segment_matched": True,
            }

    token, truncated = sanitize_path_token(src_norm)
    dst = f"{module_rel.rstrip('/')}/_imports/{token}".replace("//", "/")
    return {
        "dst": normalize_rel(dst),
        "strategy": "imports",
        "token_truncated": truncated,
        "segment_matched": False,
    }


def build_needs_followup(violation_type: str) -> List[str]:
    if violation_type == "forbidden":
        return [
            "替换对禁止区文件的直接引用",
            "校验依赖注入/配置路径",
            "更新模块 README 与变更台账",
        ]
    if violation_type == "outside_module":
        return [
            "检查包名或导入路径",
            "必要时同步构建/扫描配置",
        ]
    return ["提供 module_path 后重新生成迁移计划"]


def is_under_module_path(path_rel: str, module_rel: str) -> bool:
    path_norm = normalize_rel(path_rel).rstrip("/")
    module_norm = normalize_rel(module_rel).rstrip("/")
    return path_norm == module_norm or path_norm.startswith(module_norm + "/")


def is_reference_sensitive_path(src_rel: str) -> bool:
    src_norm = normalize_rel(src_rel)
    hot_segments = (
        "src/main/java/",
        "src/main/resources/",
        "src/main/webapp/",
    )
    return any(src_norm.startswith(seg) or f"/{seg}" in src_norm for seg in hot_segments)


def generate_rollback_plan(
    repo_root: Path,
    output_dir: Path,
    files: List[str],
    violations_by_file: Dict[str, Dict[str, Any]],
    vcs: str,
) -> Tuple[Path, Path, Path]:
    rollback_md = output_dir / "rollback_plan.md"
    rollback_sh = output_dir / "rollback_plan.sh"
    rollback_json = output_dir / "rollback_report.json"

    md_lines: List[str] = []
    md_lines.append("# rollback_plan")
    md_lines.append("")
    md_lines.append(f"- generated_at: {now_iso()}")
    md_lines.append(f"- vcs: {vcs}")
    md_lines.append(f"- file_count: {len(files)}")
    md_lines.append("")
    md_lines.append("## Files")
    if not files:
        md_lines.append("- (none)")
    else:
        for src in files:
            v = violations_by_file.get(src)
            vt = v.get("type") if isinstance(v, dict) else "none"
            md_lines.append(f"- `{src}` (violation_type={vt})")

    md_lines.append("")
    md_lines.append("## Rollback Command Strategy")
    if vcs == "git":
        md_lines.append("- tracked files: `git restore --source=HEAD -- <file>`")
        md_lines.append("- untracked files: manually remove after review")
    elif vcs == "svn":
        md_lines.append("- tracked files: `svn revert <file>`")
        md_lines.append("- unversioned files: manually remove after review")
    else:
        md_lines.append("- no VCS detected: manual rollback required")

    rollback_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    sh_lines: List[str] = []
    sh_lines.append("#!/usr/bin/env bash")
    sh_lines.append("set -euo pipefail")
    sh_lines.append(f"cd {json.dumps(str(repo_root))}")
    sh_lines.append("")
    if not files:
        sh_lines.append('echo "No files to rollback."')
    else:
        for src in files:
            if vcs == "git":
                sh_lines.append(f"if [ -e {json.dumps(src)} ] || [ -L {json.dumps(src)} ]; then")
                sh_lines.append(f"  git restore --source=HEAD -- {json.dumps(src)} || true")
                sh_lines.append("fi")
            elif vcs == "svn":
                sh_lines.append(f"if [ -e {json.dumps(src)} ] || [ -L {json.dumps(src)} ]; then")
                sh_lines.append(f"  svn revert {json.dumps(src)} || true")
                sh_lines.append("fi")
            else:
                sh_lines.append(f"echo \"[MANUAL] rollback required for {src}\"")

    rollback_sh.write_text("\n".join(sh_lines) + "\n", encoding="utf-8")
    rollback_sh.chmod(0o755)

    rollback_json.write_text(
        json.dumps(
            {
                "generated_at": now_iso(),
                "repo_root": str(repo_root),
                "vcs": vcs,
                "files": files,
                "count": len(files),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return rollback_md, rollback_sh, rollback_json


def generate_move_plan(
    repo_root: Path,
    move_output_dir: Path,
    files: List[str],
    violations_by_file: Dict[str, Dict[str, Any]],
    module_abs: Optional[Path],
    module_rel: Optional[str],
    module_source: str,
    prefer_preserve_structure: bool,
    vcs: str,
) -> Tuple[Path, Optional[Path], Path, List[Dict[str, Any]], List[str], List[str]]:
    move_md = move_output_dir / "move_plan.md"
    move_sh = move_output_dir / "move_plan.sh"
    move_json = move_output_dir / "move_report.json"

    mappings: List[Dict[str, Any]] = []
    skipped: List[str] = []
    notes: List[str] = []
    items: List[Dict[str, Any]] = []
    high_risk_flags = {
        "dst_exists",
        "path_token_truncated",
        "no_module_path",
        "dst_outside_module",
        "src_missing",
    }
    blockers: List[str] = []

    for src in files:
        violation = violations_by_file.get(src)
        if not violation:
            continue

        vtype = classify_violation(violation)

        deny_reason: Optional[str] = None
        can_move = True
        risk_flags: List[str] = []
        dst: Optional[str] = None
        dst_strategy = "none"
        token_truncated = False

        if vtype == "missing_module_path" or module_rel is None:
            can_move = False
            deny_reason = "module_path unavailable"
            risk_flags.append("no_module_path")
            blockers.append("no module_path")
        else:
            dst_meta = build_move_destination(src, module_rel, prefer_preserve_structure)
            dst = str(dst_meta["dst"])
            dst_strategy = str(dst_meta.get("strategy", "unknown"))
            token_truncated = bool(dst_meta.get("token_truncated", False))

            if token_truncated:
                risk_flags.append("path_token_truncated")
                blockers.append("path token truncated")

            if not is_under_module_path(dst, module_rel):
                can_move = False
                deny_reason = "destination is outside module_path"
                risk_flags.append("dst_outside_module")
                blockers.append("destination outside module_path")

            src_abs = (repo_root / src).resolve()
            if not src_abs.exists() and not src_abs.is_symlink():
                can_move = False
                deny_reason = "source file missing"
                risk_flags.append("src_missing")
                blockers.append("source missing")

            if dst is not None:
                dst_abs = (repo_root / dst).resolve()
                if dst_abs.exists() or dst_abs.is_symlink():
                    can_move = False
                    deny_reason = "dst exists"
                    risk_flags.append("dst_exists")
                    blockers.append("dst exists")

            if vtype in {"outside_module", "forbidden"} and is_reference_sensitive_path(src):
                risk_flags.append("needs_ref_update")

            if vtype == "forbidden":
                risk_flags.append("forbidden_zone_relocation")

        needs_followup = build_needs_followup(vtype)
        item = {
            "src": src,
            "dst": dst,
            "violation_type": vtype,
            "can_move": can_move,
            "deny_reason": deny_reason,
            "risk_flags": sorted(set(risk_flags)),
            "needs_followup": needs_followup,
            "dst_strategy": dst_strategy,
        }
        items.append(item)

        if can_move and dst and dst != src:
            reason = "outside module boundary" if vtype == "outside_module" else "forbidden zone relocation"
            mappings.append(
                {
                    "src": src,
                    "dst": dst,
                    "reason": reason,
                    "violation_type": vtype,
                    "needs_followup": needs_followup,
                }
            )
        elif deny_reason:
            skipped.append(f"{src} ({deny_reason})")

    total_items = len(items)
    movable = sum(1 for x in items if bool(x.get("can_move")))
    non_movable = max(0, total_items - movable)
    high_risk = sum(
        1
        for x in items
        if any(flag in high_risk_flags for flag in x.get("risk_flags", []))
    )
    generated = module_rel is not None
    generated_reason = "ok" if generated else "module_path unavailable"
    unique_blockers = sorted({b for b in blockers if b})

    md_lines: List[str] = []
    md_lines.append("# move_plan")
    md_lines.append("")
    md_lines.append(f"- generated_at: {now_iso()}")
    md_lines.append(f"- module_path_source: {module_source}")
    md_lines.append(f"- module_path: {str(module_abs) if module_abs else 'null'}")
    md_lines.append(f"- module_path_normalized: {module_rel if module_rel else 'null'}")
    md_lines.append(f"- prefer_preserve_structure: {str(prefer_preserve_structure).lower()}")
    md_lines.append(f"- generated: {str(generated).lower()}")
    md_lines.append(f"- generated_reason: {generated_reason}")
    md_lines.append(f"- mapping_count: {len(mappings)}")
    md_lines.append(f"- summary.total: {total_items}")
    md_lines.append(f"- summary.movable: {movable}")
    md_lines.append(f"- summary.non_movable: {non_movable}")
    md_lines.append(f"- summary.high_risk: {high_risk}")
    md_lines.append("")

    if not generated:
        md_lines.append("## Status")
        md_lines.append("- 需提供 module-path 才能生成迁移目标路径。")
        md_lines.append("- 可重新执行：`./prompt-dsl-system/tools/run.sh rollback -r . -m <MODULE_PATH> --report <GUARD_REPORT>`")
    else:
        md_lines.append("## Mappings")
        if not mappings:
            md_lines.append("- (none)")
        else:
            for m in mappings:
                md_lines.append(f"- `{m['src']}` -> `{m['dst']}` ({m['violation_type']})")
                for fol in m["needs_followup"]:
                    md_lines.append(f"  - followup: {fol}")
        md_lines.append("")
        md_lines.append("## Item Assessment")
        if not items:
            md_lines.append("- (none)")
        else:
            for item in items:
                md_lines.append(
                    f"- `{item['src']}` -> `{item['dst'] if item['dst'] else 'null'}` "
                    f"(type={item['violation_type']}, can_move={str(bool(item['can_move'])).lower()})"
                )
                if item.get("deny_reason"):
                    md_lines.append(f"  - deny_reason: {item['deny_reason']}")
                flags = item.get("risk_flags", [])
                if flags:
                    md_lines.append(f"  - risk_flags: {', '.join(flags)}")

    if skipped:
        md_lines.append("")
        md_lines.append("## Skipped")
        for item in skipped:
            md_lines.append(f"- {item}")
    if unique_blockers:
        md_lines.append("")
        md_lines.append("## Blockers")
        for b in unique_blockers:
            md_lines.append(f"- {b}")

    md_lines.append("")
    md_lines.append("## Post-move checklist")
    md_lines.append("- 修复引用路径/包名/配置")
    md_lines.append("- 更新模块 README 与变更台账")
    md_lines.append("- 重新运行 `debug-guard` 检查边界")

    move_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    move_shell_path: Optional[Path] = None
    if generated and mappings:
        sh_lines: List[str] = []
        sh_lines.append("#!/usr/bin/env bash")
        sh_lines.append("set -euo pipefail")
        sh_lines.append(f"cd {json.dumps(str(repo_root))}")
        sh_lines.append("")
        sh_lines.append('echo "Applying move plan (safe checks enabled)..."')

        for m in mappings:
            src = m["src"]
            dst = m["dst"]
            dst_parent = str(Path(dst).parent).replace("\\", "/")
            sh_lines.append(f"if [ ! -e {json.dumps(src)} ] && [ ! -L {json.dumps(src)} ]; then")
            sh_lines.append(f"  echo \"[ERROR] source missing: {src}\" >&2")
            sh_lines.append("  exit 2")
            sh_lines.append("fi")
            sh_lines.append(f"mkdir -p {json.dumps(dst_parent)}")
            sh_lines.append(f"if [ -e {json.dumps(dst)} ] || [ -L {json.dumps(dst)} ]; then")
            sh_lines.append(f"  echo \"[ERROR] destination exists: {dst}\" >&2")
            sh_lines.append("  exit 2")
            sh_lines.append("fi")
            if vcs == "git":
                sh_lines.append(f"git mv {json.dumps(src)} {json.dumps(dst)}")
            elif vcs == "svn":
                sh_lines.append(f"svn mv {json.dumps(src)} {json.dumps(dst)}")
            else:
                sh_lines.append(f"mv {json.dumps(src)} {json.dumps(dst)}")
            sh_lines.append("")

        move_sh.write_text("\n".join(sh_lines) + "\n", encoding="utf-8")
        move_sh.chmod(0o755)
        move_shell_path = move_sh
    elif move_sh.exists():
        move_sh.unlink()

    allow_prefixes: List[str] = ["prompt-dsl-system/"]
    if module_rel:
        allow_prefixes.append(f"{module_rel.rstrip('/')}/")

    move_json.write_text(
        json.dumps(
            {
                "generated_at": now_iso(),
                "repo_root": str(repo_root),
                "module_path": str(module_abs) if module_abs else None,
                "module_path_normalized": module_rel,
                "module_path_source": module_source,
                "generated": generated,
                "generated_reason": generated_reason,
                "vcs": vcs,
                "effective_allowlist_prefixes": allow_prefixes,
                "items": items,
                "summary": {
                    "total": total_items,
                    "movable": movable,
                    "non_movable": non_movable,
                    "high_risk": high_risk,
                },
                "blockers": unique_blockers,
                "move_plan_available": bool(generated and total_items > 0),
                "mappings": mappings,
                "skipped": skipped,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return move_md, move_shell_path, move_json, mappings, skipped, notes


def run_apply_move(
    repo_root: Path,
    mappings: List[Dict[str, Any]],
    vcs: str,
) -> Tuple[bool, List[Dict[str, Any]], Optional[str]]:
    logs: List[Dict[str, Any]] = []

    for m in mappings:
        src = m["src"]
        dst = m["dst"]
        src_abs = (repo_root / src).resolve()
        dst_abs = (repo_root / dst).resolve()

        if vcs == "git":
            cmd = ["git", "mv", src, dst]
        elif vcs == "svn":
            cmd = ["svn", "mv", src, dst]
        else:
            cmd = ["mv", src, dst]

        log_item: Dict[str, Any] = {
            "src": src,
            "dst": dst,
            "command": " ".join(cmd),
            "status": "pending",
            "message": "",
        }
        logs.append(log_item)

        if not src_abs.exists() and not src_abs.is_symlink():
            log_item["status"] = "failed"
            log_item["message"] = f"source missing: {src}"
            return False, logs, f"source missing: {src}"
        if dst_abs.exists() or dst_abs.is_symlink():
            log_item["status"] = "conflict"
            log_item["message"] = f"destination exists: {dst}"
            return False, logs, f"destination exists: {dst}"

        dst_abs.parent.mkdir(parents=True, exist_ok=True)

        proc = subprocess.run(cmd, cwd=str(repo_root), text=True, capture_output=True)
        if proc.returncode != 0:
            detail = proc.stderr.strip() or proc.stdout.strip() or "unknown error"
            log_item["status"] = "failed"
            log_item["message"] = f"move failed: {detail}"
            return False, logs, f"move failed ({' '.join(cmd)}): {detail}"

        log_item["status"] = "success"
        log_item["message"] = "ok"

    return True, logs, None


def write_move_apply_log(
    log_path: Path,
    repo_root: Path,
    vcs: str,
    requested: bool,
    executed: bool,
    move_dry_run: bool,
    yes_flag: bool,
    module_rel: Optional[str],
    result_ok: bool,
    result_message: str,
    logs: List[Dict[str, Any]],
) -> None:
    lines: List[str] = []
    lines.append("# move_apply_log")
    lines.append("")
    lines.append(f"- generated_at: {now_iso()}")
    lines.append(f"- repo_root: {repo_root}")
    lines.append(f"- vcs: {vcs}")
    lines.append(f"- requested_apply: {str(requested).lower()}")
    lines.append(f"- executed: {str(executed).lower()}")
    lines.append(f"- move_dry_run: {str(move_dry_run).lower()}")
    lines.append(f"- yes: {str(yes_flag).lower()}")
    lines.append(f"- module_path_normalized: {module_rel if module_rel else 'null'}")
    lines.append(f"- result: {'success' if result_ok else 'failed'}")
    lines.append(f"- message: {result_message}")
    lines.append("")
    lines.append("## Command Execution")
    if not logs:
        lines.append("- (none)")
    else:
        for idx, item in enumerate(logs, start=1):
            cmd = str(item.get("command", ""))
            status = str(item.get("status", "unknown"))
            msg = str(item.get("message", ""))
            lines.append(f"{idx}. `{cmd}`")
            lines.append(f"   - status: {status}")
            if msg:
                lines.append(f"   - message: {msg}")

    lines.append("")
    lines.append("## Verification")
    if vcs == "git":
        lines.append("- `git status`")
    elif vcs == "svn":
        lines.append("- `svn status`")
    else:
        lines.append("- 手工核对文件是否按 move_plan 迁移")
    lines.append("- `./prompt-dsl-system/tools/run.sh debug-guard -r . -m <MODULE_PATH>`")

    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate rollback + move plans from guard report")
    p.add_argument("--repo-root", default=".", help="Repository root path")
    p.add_argument(
        "--report",
        default="prompt-dsl-system/tools/guard_report.json",
        help="Path to guard_report.json (repo-relative or absolute)",
    )
    p.add_argument(
        "--output-dir",
        default="prompt-dsl-system/tools",
        help="Directory for rollback outputs",
    )
    p.add_argument("--only-violations", default="false", help="Use only violations as source files (true/false)")
    p.add_argument("--emit", choices=["both", "move", "rollback"], default="both")
    p.add_argument(
        "--mode",
        choices=["plan", "apply"],
        default="plan",
        help="plan: generate only (default), apply: same as move-mode=apply",
    )

    p.add_argument("--module-path", help="Optional module boundary path")
    p.add_argument("--move-mode", choices=["suggest", "apply"], default="suggest")
    p.add_argument(
        "--move-output-dir",
        help="Directory for move plan outputs (default: output-dir)",
    )
    p.add_argument("--move-dry-run", default="true", help="true/false, default true")
    p.add_argument(
        "--prefer-preserve-structure",
        default="true",
        help="true/false, default true",
    )
    p.add_argument("--yes", action="store_true", help="Required with --move-mode apply and --move-dry-run=false")
    p.add_argument("--apply-move", default="false", help="true/false, shortcut for --emit move + --move-mode apply")
    p.add_argument("--plan-only", default="false", help="true/false, force plan generation only (no apply)")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        print(f"Invalid repo root: {repo_root}", file=sys.stderr)
        return 2

    try:
        report_path = resolve_under_repo(args.report, repo_root, require_exists=True)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        report = load_guard_report(report_path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    only_violations = parse_bool(args.only_violations, default=False)
    move_dry_run = parse_bool(args.move_dry_run, default=True)
    prefer_preserve = parse_bool(args.prefer_preserve_structure, default=True)
    apply_move_requested = parse_bool(args.apply_move, default=False)
    plan_only = parse_bool(args.plan_only, default=False)
    emit = args.emit

    move_mode = args.move_mode
    apply_requested = move_mode == "apply"
    if args.mode == "apply":
        move_mode = "apply"
        apply_requested = True
    if apply_move_requested:
        emit = "move"
        move_mode = "apply"
        apply_requested = True
    if plan_only:
        move_mode = "suggest"

    try:
        output_dir = resolve_under_repo(args.output_dir, repo_root, require_exists=False)
        move_output_raw = args.move_output_dir if args.move_output_dir else args.output_dir
        move_output_dir = resolve_under_repo(move_output_raw, repo_root, require_exists=False)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)
    move_output_dir.mkdir(parents=True, exist_ok=True)

    module_abs: Optional[Path]
    module_rel: Optional[str]
    module_source: str
    module_warnings: List[str]
    module_abs, module_rel, module_source, module_warnings = resolve_module_path(
        args.module_path, report, repo_root
    )

    files, violations_by_file = collect_targets(report, only_violations=only_violations)
    vcs = detect_vcs(repo_root, report)

    rollback_md: Optional[Path] = None
    rollback_sh: Optional[Path] = None
    rollback_json: Optional[Path] = None
    if emit in {"both", "rollback"}:
        rollback_md, rollback_sh, rollback_json = generate_rollback_plan(
            repo_root=repo_root,
            output_dir=output_dir,
            files=files,
            violations_by_file=violations_by_file,
            vcs=vcs,
        )
    else:
        for stale in (
            output_dir / "rollback_plan.md",
            output_dir / "rollback_plan.sh",
            output_dir / "rollback_report.json",
        ):
            if stale.exists():
                stale.unlink()

    move_md: Optional[Path] = None
    move_sh: Optional[Path] = None
    move_json: Optional[Path] = None
    mappings: List[Dict[str, Any]] = []
    skipped: List[str] = []
    if emit in {"both", "move"}:
        move_md, move_sh, move_json, mappings, skipped, _notes = generate_move_plan(
            repo_root=repo_root,
            move_output_dir=move_output_dir,
            files=files,
            violations_by_file=violations_by_file,
            module_abs=module_abs,
            module_rel=module_rel,
            module_source=module_source,
            prefer_preserve_structure=prefer_preserve,
            vcs=vcs,
        )
    else:
        for stale in (
            move_output_dir / "move_plan.md",
            move_output_dir / "move_plan.sh",
            move_output_dir / "move_report.json",
        ):
            if stale.exists():
                stale.unlink()

    if module_warnings:
        for w in module_warnings:
            print(f"[rollback][warn] {w}")

    move_apply_log_path = move_output_dir / "move_apply_log.md"
    if apply_requested and move_apply_log_path.exists():
        move_apply_log_path.unlink()

    if apply_requested:
        executed = False
        apply_logs: List[Dict[str, Any]] = []
        result_ok = False
        result_msg = "not executed"

        if plan_only:
            result_ok = True
            result_msg = "plan-only=true, skipped move execution"
            write_move_apply_log(
                log_path=move_apply_log_path,
                repo_root=repo_root,
                vcs=vcs,
                requested=True,
                executed=False,
                move_dry_run=move_dry_run,
                yes_flag=args.yes,
                module_rel=module_rel,
                result_ok=result_ok,
                result_message=result_msg,
                logs=apply_logs,
            )
            print("[rollback] plan-only=true: generated plans only, no file moves executed")
        else:
            if emit == "rollback":
                result_msg = "apply requested but emit=rollback prevents move execution"
            elif module_abs is None or module_rel is None:
                result_msg = "module-path is required for apply move; provide -m/--module-path"
            elif not module_abs.exists() or not module_abs.is_dir():
                result_msg = f"module-path is not an existing directory: {module_abs}"
            elif move_dry_run:
                result_msg = "move execution requires --move-dry-run=false"
            elif not args.yes:
                result_msg = "move execution requires --yes confirmation"
            elif move_md is None or move_json is None:
                result_msg = "move artifacts were not generated; cannot apply move"
            elif move_sh is None and mappings:
                result_msg = "move_plan.sh not generated; cannot safely apply move"
            elif not mappings:
                result_ok = True
                result_msg = "no move mappings, nothing to apply"
            else:
                ok, apply_logs, error_message = run_apply_move(
                    repo_root=repo_root,
                    mappings=mappings,
                    vcs=vcs,
                )
                if ok:
                    executed = True
                    result_ok = True
                    result_msg = "move apply completed"
                else:
                    result_msg = error_message or "move apply failed"

            write_move_apply_log(
                log_path=move_apply_log_path,
                repo_root=repo_root,
                vcs=vcs,
                requested=True,
                executed=executed,
                move_dry_run=move_dry_run,
                yes_flag=args.yes,
                module_rel=module_rel,
                result_ok=result_ok,
                result_message=result_msg,
                logs=apply_logs,
            )

            if not result_ok:
                print(f"[rollback][error] {result_msg}", file=sys.stderr)
                return 2

            if executed:
                print("[rollback] move apply completed")
                if vcs == "git":
                    print("[rollback] verify: git status")
                elif vcs == "svn":
                    print("[rollback] verify: svn status")
                else:
                    print("[rollback] verify moved files manually")
                print("[rollback] recheck: ./prompt-dsl-system/tools/run.sh debug-guard -r . -m <MODULE_PATH>")

    print("Rollback/Move Plan generated")
    print(f"- report: {to_repo_relative(report_path, repo_root)}")
    if rollback_md is not None and rollback_sh is not None and rollback_json is not None:
        print(f"- rollback_plan.md: {to_repo_relative(rollback_md, repo_root)}")
        print(f"- rollback_plan.sh: {to_repo_relative(rollback_sh, repo_root)}")
        print(f"- rollback_report.json: {to_repo_relative(rollback_json, repo_root)}")
    else:
        print("- rollback artifacts: not generated (emit=move)")

    if move_md is not None and move_json is not None:
        print(f"- move_plan.md: {to_repo_relative(move_md, repo_root)}")
        if move_sh is not None:
            print(f"- move_plan.sh: {to_repo_relative(move_sh, repo_root)}")
        else:
            print("- move_plan.sh: not generated (module-path unavailable or no move targets)")
        print(f"- move_report.json: {to_repo_relative(move_json, repo_root)}")
        print(f"- move_mapping_count: {len(mappings)}")
        print(f"- move_skipped_count: {len(skipped)}")
    else:
        print("- move artifacts: not generated (emit=rollback)")

    if move_apply_log_path.exists():
        print(f"- move_apply_log.md: {to_repo_relative(move_apply_log_path, repo_root)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
