#!/usr/bin/env python3
"""Project stack scanner for Hongzhi project knowledge base.

Scans a target repository and emits a discovered stack profile YAML:
  prompt-dsl-system/project_stacks/<project_key>/stack_profile.discovered.yaml

Standard-library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set, Tuple

SCANNER_VERSION = "1.0.0"

IGNORE_DIRS = {
    ".git",
    ".svn",
    "node_modules",
    "target",
    "dist",
    "build",
    "out",
    "__pycache__",
    ".idea",
    ".gradle",
    ".mvn",
}

TEXT_FILE_HINTS = {
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
    "package.json",
    "application.yml",
    "application.yaml",
    "application.properties",
    "bootstrap.yml",
    "bootstrap.yaml",
    "bootstrap.properties",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def quote_yaml(value: str) -> str:
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def detect_java_runtime(content: str) -> str:
    patterns = [
        r"<maven\.compiler\.source>\s*([^<]+)\s*</maven\.compiler\.source>",
        r"<maven\.compiler\.target>\s*([^<]+)\s*</maven\.compiler\.target>",
        r"<java\.version>\s*([^<]+)\s*</java\.version>",
        r"sourceCompatibility\s*=\s*['\"]([^'\"]+)['\"]",
        r"targetCompatibility\s*=\s*['\"]([^'\"]+)['\"]",
    ]
    for pattern in patterns:
        match = re.search(pattern, content)
        if not match:
            continue
        raw = match.group(1).strip().lower()
        if raw in {"1.8", "8", "java8"}:
            return "java8"
        if raw.startswith("1."):
            return f"java{raw.split('.', 1)[1]}"
        if raw.isdigit():
            return f"java{raw}"
        return raw
    return "unknown"


def append_evidence(evidences: List[dict], signal: str, detail: str, file_path: str) -> None:
    evidences.append(
        {
            "signal": signal,
            "detail": detail,
            "file": file_path,
        }
    )


def add_fact(bucket: Set[str], value: str, evidences: List[dict], signal: str, detail: str, file_path: str) -> None:
    if value not in bucket:
        bucket.add(value)
    append_evidence(evidences, signal=signal, detail=detail, file_path=file_path)


def maybe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def scan_project(repo_root: Path, max_files: int) -> Tuple[dict, List[dict], int, str]:
    stack = {
        "backend_languages": set(),
        "backend_frameworks": set(),
        "frontend_frameworks": set(),
        "ui_frameworks": set(),
        "mobile_frameworks": set(),
        "database_engines": set(),
        "process_engines": set(),
        "build_tools": set(),
        "vcs": set(),
    }
    evidences: List[dict] = []
    java_runtime = "unknown"

    if (repo_root / ".git").is_dir():
        add_fact(stack["vcs"], "git", evidences, "vcs_marker", ".git directory detected", ".git")
    if (repo_root / ".svn").is_dir():
        add_fact(stack["vcs"], "svn", evidences, "vcs_marker", ".svn directory detected", ".svn")

    scanned = 0
    for path in repo_root.rglob("*"):
        if scanned >= max_files:
            break
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue

        scanned += 1
        rel = str(path.relative_to(repo_root)).replace("\\", "/")
        name = path.name.lower()
        suffix = path.suffix.lower()

        if suffix == ".java":
            stack["backend_languages"].add("java")

        if suffix == ".kt":
            add_fact(stack["backend_languages"], "kotlin", evidences, "file_extension", "Kotlin source", rel)
        if suffix == ".py":
            add_fact(stack["backend_languages"], "python", evidences, "file_extension", "Python source", rel)
        if suffix in {".js", ".jsx"}:
            stack["ui_frameworks"].add("javascript")
        if suffix in {".ts", ".tsx"}:
            add_fact(stack["ui_frameworks"], "typescript", evidences, "file_extension", "TypeScript source", rel)
        if suffix == ".vue":
            add_fact(stack["frontend_frameworks"], "vue.js", evidences, "file_extension", "Vue SFC", rel)
        if suffix in {".html", ".htm"}:
            stack["ui_frameworks"].add("html")
        if suffix == ".bpmn":
            add_fact(stack["process_engines"], "activiti", evidences, "file_extension", "BPMN process file", rel)

        should_parse = name in TEXT_FILE_HINTS
        if not should_parse and suffix in {".xml", ".properties", ".yml", ".yaml", ".js", ".vue", ".sql"}:
            # Parse targeted text-like files for framework/db signals.
            should_parse = True
        if not should_parse:
            continue

        content = maybe_read_text(path)
        if not content:
            continue

        lower = content.lower()

        if name == "pom.xml":
            add_fact(stack["build_tools"], "maven", evidences, "build_file", "pom.xml detected", rel)
            runtime = detect_java_runtime(content)
            if runtime != "unknown":
                java_runtime = runtime
                append_evidence(evidences, "java_runtime", f"{runtime} from pom.xml", rel)

        if name in {"build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"}:
            add_fact(stack["build_tools"], "gradle", evidences, "build_file", f"{name} detected", rel)
            runtime = detect_java_runtime(content)
            if java_runtime == "unknown" and runtime != "unknown":
                java_runtime = runtime
                append_evidence(evidences, "java_runtime", f"{runtime} from gradle", rel)

        if name == "package.json":
            add_fact(stack["build_tools"], "npm", evidences, "build_file", "package.json detected", rel)
            try:
                package_data = json.loads(content)
            except json.JSONDecodeError:
                package_data = {}
            deps = {}
            for dep_key in ("dependencies", "devDependencies", "peerDependencies"):
                raw_deps = package_data.get(dep_key, {})
                if isinstance(raw_deps, dict):
                    deps.update({str(k).lower(): str(v) for k, v in raw_deps.items()})
            if any(k == "vue" or k.startswith("@vue/") for k in deps):
                add_fact(stack["frontend_frameworks"], "vue.js", evidences, "package_dependency", "vue dependency", rel)
            if any("@dcloudio" in k or "uni-app" in k for k in deps):
                add_fact(stack["mobile_frameworks"], "uni-app", evidences, "package_dependency", "uni-app dependency", rel)

        if "spring-boot-starter" in lower or "@springbootapplication" in lower:
            add_fact(stack["backend_frameworks"], "spring-boot", evidences, "framework_signal", "spring boot marker", rel)
        elif "org.springframework" in lower or "@restcontroller" in lower or "@controller" in lower:
            add_fact(stack["backend_frameworks"], "spring", evidences, "framework_signal", "spring marker", rel)

        if "mybatis" in lower:
            add_fact(stack["backend_frameworks"], "mybatis", evidences, "framework_signal", "mybatis marker", rel)
        if "mybatis-plus" in lower:
            add_fact(stack["backend_frameworks"], "mybatis-plus", evidences, "framework_signal", "mybatis-plus marker", rel)
        if "lombok" in lower:
            add_fact(stack["backend_frameworks"], "lombok", evidences, "framework_signal", "lombok marker", rel)

        if "activiti" in lower:
            add_fact(stack["process_engines"], "activiti", evidences, "process_signal", "activiti marker", rel)

        if "layui" in lower:
            add_fact(stack["ui_frameworks"], "layui", evidences, "ui_signal", "layui marker", rel)

        if "jdbc:oracle:" in lower or "ojdbc" in lower:
            add_fact(stack["database_engines"], "oracle", evidences, "db_signal", "oracle jdbc/dependency marker", rel)
        if "jdbc:mysql:" in lower or "mysql-connector" in lower:
            add_fact(stack["database_engines"], "mysql", evidences, "db_signal", "mysql jdbc/dependency marker", rel)
        if "jdbc:dm:" in lower or "jdbc:dm8:" in lower or "dm.jdbc.driver.dmdriver" in lower:
            add_fact(stack["database_engines"], "dm8", evidences, "db_signal", "dm jdbc/dependency marker", rel)

        if "restful" in lower or "@requestmapping" in lower or "@getmapping" in lower or "@postmapping" in lower:
            add_fact(stack["backend_frameworks"], "restful-api", evidences, "api_signal", "REST mapping marker", rel)

    return stack, evidences, scanned, java_runtime


def compute_confidence(stack: dict, evidences: List[dict]) -> Tuple[str, float, List[str]]:
    non_empty_categories = sum(1 for _k, v in stack.items() if v)
    evidence_count = len(evidences)
    score = min(1.0, non_empty_categories * 0.08 + min(40, evidence_count) * 0.015)

    notes: List[str] = []
    if evidence_count < 8:
        notes.append("Evidence density is low; provide additional repo inputs.")
    if non_empty_categories < 4:
        notes.append("Detected stack coverage is narrow; run scanner on full project root.")

    if score >= 0.75:
        level = "high"
    elif score >= 0.45:
        level = "medium"
    else:
        level = "low"
    return level, round(score, 3), notes


def build_required_info(stack: dict, java_runtime: str) -> List[str]:
    required: List[str] = []
    if not stack["database_engines"]:
        required.append("Database engine evidence is missing; provide datasource config or SQL scripts.")
    if java_runtime == "unknown" and "java" in stack["backend_languages"]:
        required.append("Java runtime version is unknown; provide pom.xml/build.gradle compiler target.")
    if not stack["vcs"]:
        required.append("VCS type is unknown; provide repository metadata.")
    if not stack["backend_frameworks"]:
        required.append("Backend framework evidence is missing; provide framework config files.")
    return required


def dump_yaml(
    project_key: str,
    repo_root: Path,
    stack: dict,
    evidences: List[dict],
    scanned_files: int,
    java_runtime: str,
) -> str:
    confidence_level, confidence_score, confidence_notes = compute_confidence(stack, evidences)
    required_info = build_required_info(stack, java_runtime)

    lines: List[str] = []
    lines.append("# Auto-generated by project_stack_scanner.py — DO NOT EDIT MANUALLY")
    lines.append("")
    lines.append('profile_kind: "discovered"')
    lines.append('profile_version: "1.0"')
    lines.append("")
    lines.append("identity:")
    lines.append(f"  project_key: {quote_yaml(project_key)}")
    lines.append(f"  profile_id: {quote_yaml(f'{project_key}/stack')}")
    lines.append("")
    lines.append("discovery:")
    lines.append(f"  generated_at: {quote_yaml(now_iso())}")
    lines.append(f"  scanner_version: {quote_yaml(SCANNER_VERSION)}")
    lines.append(f"  target_repo_root: {quote_yaml(str(repo_root))}")
    lines.append(f"  file_count: {scanned_files}")
    lines.append("  evidence:")

    if evidences:
        for item in evidences[:120]:
            lines.append(f"    - signal: {quote_yaml(item['signal'])}")
            lines.append(f"      detail: {quote_yaml(item['detail'])}")
            lines.append(f"      file: {quote_yaml(item['file'])}")
    else:
        lines.append("    []")

    lines.append("")
    lines.append("stack:")
    ordered_keys = [
        "backend_languages",
        "backend_frameworks",
        "frontend_frameworks",
        "ui_frameworks",
        "mobile_frameworks",
        "database_engines",
        "process_engines",
        "build_tools",
        "vcs",
    ]
    for key in ordered_keys:
        values = sorted(str(x) for x in stack[key])
        if values:
            lines.append(f"  {key}:")
            for value in values:
                lines.append(f"    - {quote_yaml(value)}")
        else:
            lines.append(f"  {key}: []")

    lines.append("")
    lines.append("constraints:")
    lines.append(f"  java_runtime: {quote_yaml(java_runtime)}")
    lines.append('  sql_policy: "portable_first_dual_sql_when_needed"')

    lines.append("")
    lines.append("confidence:")
    lines.append(f"  overall: {quote_yaml(confidence_level)}")
    lines.append(f"  score: {confidence_score}")
    lines.append("  notes:")
    if confidence_notes:
        for note in confidence_notes:
            lines.append(f"    - {quote_yaml(note)}")
    else:
        lines.append("    []")

    lines.append("")
    lines.append("required_additional_information:")
    if required_info:
        for item in required_info:
            lines.append(f"  - {quote_yaml(item)}")
    else:
        lines.append("  []")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan repository and generate discovered stack profile")
    parser.add_argument("--repo-root", required=True, help="Target project repository root to scan")
    parser.add_argument("--project-key", required=True, help="Project key, e.g. xywygl")
    parser.add_argument(
        "--kit-root",
        default=None,
        help="beyond-dev-ai-kit root. Default: infer from script path",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output YAML path. Default: <kit-root>/prompt-dsl-system/project_stacks/<project_key>/stack_profile.discovered.yaml",
    )
    parser.add_argument("--max-files", type=int, default=20000, help="Maximum files to scan")
    parser.add_argument("--read-only", action="store_true", help="Print to stdout only")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    if not repo_root.is_dir():
        print(f"[stack_scanner] FAIL: repo-root not found: {repo_root}", file=sys.stderr)
        return 2

    if args.kit_root:
        kit_root = Path(args.kit_root).expanduser().resolve()
    else:
        kit_root = Path(__file__).resolve().parents[2]

    if args.out:
        out_path = Path(args.out).expanduser().resolve()
    else:
        out_path = (
            kit_root
            / "prompt-dsl-system"
            / "project_stacks"
            / args.project_key
            / "stack_profile.discovered.yaml"
        )

    stack, evidences, scanned_files, java_runtime = scan_project(repo_root, max_files=max(1, args.max_files))
    rendered = dump_yaml(
        project_key=args.project_key,
        repo_root=repo_root,
        stack=stack,
        evidences=evidences,
        scanned_files=scanned_files,
        java_runtime=java_runtime,
    )

    if args.read_only:
        print(rendered, end="")
        print(
            f"[stack_scanner] project={args.project_key} files={scanned_files} evidence={len(evidences)} mode=stdout",
            file=sys.stderr,
        )
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    print(f"[stack_scanner] output: {out_path}")
    print(f"[stack_scanner] project={args.project_key} files={scanned_files} evidence={len(evidences)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
