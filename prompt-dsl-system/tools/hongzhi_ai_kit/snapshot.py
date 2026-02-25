#!/usr/bin/env python3
"""Snapshot-based read-only contract enforcement.

Extracted from hongzhi_plugin.py for modularity.
Provides lightweight file-system snapshot, diff, and read-only guard.
"""

from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional, Tuple


SNAPSHOT_EXCLUDES = {
    ".git", ".idea", ".DS_Store", "target", "build", "node_modules",
    "__pycache__", ".gradle", ".mvn", "dist", "out"
}
SNAPSHOT_EXT_EXCLUDES = {
    ".class", ".jar", ".war", ".ear", ".zip", ".tar.gz", ".pyc"
}


def take_snapshot(repo_root, max_files=None) -> Dict[str, Tuple[int, int]]:
    """Lightweight snapshot: {relpath: (size, mtime_ns)} for files under repo_root."""
    snap: Dict[str, Tuple[int, int]] = {}
    count = 0
    for root, dirs, files in os.walk(str(repo_root)):
        dirs[:] = [d for d in dirs if d not in SNAPSHOT_EXCLUDES]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in SNAPSHOT_EXT_EXCLUDES:
                continue
            fp = os.path.join(root, f)
            try:
                st = os.stat(fp)
                rel = os.path.relpath(fp, str(repo_root))
                snap[rel] = (st.st_size, st.st_mtime_ns)
            except OSError:
                pass
            count += 1
            if max_files and count >= max_files:
                return snap  # early stop
    return snap


def diff_snapshots(before, after) -> Dict[str, List[str]]:
    """Compare two snapshots, return dict of created/deleted/modified files."""
    created = []
    deleted = []
    modified = []
    for rel in after:
        if rel not in before:
            created.append(rel)
        elif after[rel] != before[rel]:
            modified.append(rel)
    for rel in before:
        if rel not in after:
            deleted.append(rel)
    return {"created": created, "deleted": deleted, "modified": modified}


def enforce_read_only(delta, write_ok):
    """If write_ok is False and delta is non-empty, FAIL with exit code 3."""
    total = len(delta["created"]) + len(delta["deleted"]) + len(delta["modified"])
    if total == 0:
        return True
    if write_ok:
        print(f"[plugin] NOTE: {total} file(s) changed in project repo (--write-ok active)",
              file=sys.stderr)
        return True
    print(f"[plugin] FAIL: read-only contract violated — {total} file(s) changed in project repo:",
          file=sys.stderr)
    for cat in ("created", "deleted", "modified"):
        for f in delta[cat][:5]:
            print(f"  [{cat}] {f}", file=sys.stderr)
    sys.exit(3)
