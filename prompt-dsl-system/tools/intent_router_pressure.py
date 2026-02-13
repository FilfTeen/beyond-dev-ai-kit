#!/usr/bin/env python3
"""High-pressure invariant checks for intent_router.

This script is deterministic and CI-friendly:
- randomized but seeded single-thread routing flood
- concurrent routing flood
- explicit-pipeline precedence checks
- long-input robustness check
"""

from __future__ import annotations

import argparse
import json
import random
import string
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from intent_router import choose_action


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="intent_router pressure and invariant checks")
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument("--seed", type=int, default=20260213, help="Deterministic random seed")
    parser.add_argument("--single-calls", type=int, default=6000, help="Single-thread routed calls")
    parser.add_argument("--concurrent-calls", type=int, default=8000, help="Concurrent routed calls")
    parser.add_argument("--concurrency", type=int, default=32, help="Thread worker count")
    parser.add_argument("--max-p99-ms", type=float, default=8.0, help="Fail if single-thread p99 exceeds this")
    parser.add_argument("--max-single-errors", type=int, default=0, help="Fail if single-thread errors exceed this")
    parser.add_argument("--max-concurrent-errors", type=int, default=0, help="Fail if concurrent errors exceed this")
    parser.add_argument("--out-json", default="", help="Optional JSON report output path")
    return parser.parse_args()


def percentile(sorted_values: List[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, int(len(sorted_values) * q))
    return sorted_values[idx]


def make_goal(rng: random.Random, idx: int) -> str:
    pipelines = [
        "pipeline_ownercommittee_audit_fix.md",
        "pipeline_skill_creator.md",
        "pipeline_kit_self_upgrade.md",
    ]
    keywords = [
        "修复",
        "改进",
        "模块",
        "ownercommittee",
        "self-upgrade",
        "validate",
        "自升级",
        "治理",
        "registry",
        "baseline",
        "sql",
        "oracle",
        "dm8",
        "bug",
    ]
    mode = idx % 9
    noise = "".join(rng.choice(string.ascii_letters + string.digits) for _ in range(rng.randint(12, 80)))
    if mode == 0:
        return f"请执行 {rng.choice(pipelines)} 并给出计划 {noise}"
    if mode == 1:
        return f"执行 beyond-dev-ai-kit 自升级并走严格前置校验 {noise}"
    if mode == 2:
        return f"修复 ownercommittee 模块状态流转问题，最小改动 {noise}"
    if mode == 3:
        return f"module_path=\"/tmp/mod_{idx}\" 修复接口错误 {noise}"
    if mode == 4:
        return f"module_path='/tmp/mod_{idx}' 做完整性验证和查漏补缺 {noise}"
    if mode == 5:
        return f"请处理 /tmp/mod_{idx}。并验证 {noise}"
    if mode == 6:
        return f"请处理 ./module_{idx}); 并验证 {noise}"
    if mode == 7:
        return " ".join(rng.choice(keywords) for _ in range(rng.randint(8, 24))) + f" {noise}"
    return f"{noise} {' '.join(rng.choice(keywords) for _ in range(16))}"


def validate_selected(payload: Dict[str, Any]) -> bool:
    selected = payload.get("selected", {})
    action_kind = selected.get("action_kind")
    target = str(selected.get("target", "")).strip()
    confidence = float(selected.get("confidence", 0.0))
    if action_kind not in {"pipeline", "command"}:
        return False
    if not target:
        return False
    if confidence < 0.0 or confidence > 1.0:
        return False
    return True


def run_pressure(args: argparse.Namespace) -> Dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    rng = random.Random(args.seed)

    single_lat_ms: List[float] = []
    single_errors = 0
    for idx in range(int(args.single_calls)):
        goal = make_goal(rng, idx)
        started = time.perf_counter()
        try:
            routed = choose_action(goal, repo_root)
            if not validate_selected(routed):
                single_errors += 1
            if "pipeline_" in goal:
                requested = goal.split("pipeline_", 1)[1].split(".md", 1)[0]
                selected_target = str(routed["selected"]["target"])
                if f"pipeline_{requested}.md" not in selected_target:
                    single_errors += 1
        except Exception:
            single_errors += 1
        single_lat_ms.append((time.perf_counter() - started) * 1000.0)

    long_goal = ("噪声" * 50000) + " 请执行 pipeline_skill_creator.md 并给出计划"
    long_started = time.perf_counter()
    long_payload = choose_action(long_goal, repo_root)
    long_ms = (time.perf_counter() - long_started) * 1000.0
    long_ok = str(long_payload["selected"]["target"]).endswith("pipeline_skill_creator.md")

    concurrent_errors = 0
    concurrent_started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=int(args.concurrency)) as executor:
        futures = [
            executor.submit(choose_action, make_goal(rng, idx + 200000), repo_root)
            for idx in range(int(args.concurrent_calls))
        ]
        for fut in as_completed(futures):
            try:
                payload = fut.result()
                if not validate_selected(payload):
                    concurrent_errors += 1
            except Exception:
                concurrent_errors += 1
    concurrent_seconds = time.perf_counter() - concurrent_started

    single_lat_ms.sort()
    report: Dict[str, Any] = {
        "single_thread_calls": int(args.single_calls),
        "single_thread_errors": int(single_errors),
        "single_thread_latency_ms": {
            "p50": round(percentile(single_lat_ms, 0.50), 3),
            "p95": round(percentile(single_lat_ms, 0.95), 3),
            "p99": round(percentile(single_lat_ms, 0.99), 3),
            "max": round(single_lat_ms[-1] if single_lat_ms else 0.0, 3),
        },
        "concurrent_calls": int(args.concurrent_calls),
        "concurrency": int(args.concurrency),
        "concurrent_seconds": round(concurrent_seconds, 3),
        "concurrent_errors": int(concurrent_errors),
        "long_input_ms": round(long_ms, 3),
        "long_input_ok": bool(long_ok),
        "seed": int(args.seed),
    }
    return report


def main() -> int:
    args = parse_args()
    report = run_pressure(args)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    out_json = str(args.out_json or "").strip()
    if out_json:
        out_path = Path(out_json)
        if not out_path.is_absolute():
            out_path = (Path.cwd() / out_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    fail_reasons: List[str] = []
    p99 = float(report["single_thread_latency_ms"]["p99"])
    if int(report["single_thread_errors"]) > int(args.max_single_errors):
        fail_reasons.append("single_thread_errors_exceeded")
    if int(report["concurrent_errors"]) > int(args.max_concurrent_errors):
        fail_reasons.append("concurrent_errors_exceeded")
    if p99 > float(args.max_p99_ms):
        fail_reasons.append("single_thread_p99_exceeded")
    if not bool(report["long_input_ok"]):
        fail_reasons.append("long_input_route_incorrect")

    if fail_reasons:
        print(f"[intent_pressure][FAIL] reasons={','.join(fail_reasons)}", file=sys.stderr)
        return 21
    print("[intent_pressure][PASS]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
