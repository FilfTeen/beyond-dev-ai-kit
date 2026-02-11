"""Path resolution helpers for workspace and global capability state."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


def _is_accessible_dir(path: Path, require_write: bool) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    if require_write:
        return os.access(path, os.W_OK | os.X_OK)
    return os.access(path, os.R_OK | os.X_OK)


def _first_existing_root(candidates: Iterable[Path]) -> Path | None:
    for base in candidates:
        try:
            resolved = base.expanduser()
            if _is_accessible_dir(resolved, require_write=False):
                return resolved
        except OSError:
            continue
    return None


def _first_writable_root(candidates: Iterable[Path], create: bool = True) -> Path:
    resolved_candidates = [Path(c).expanduser() for c in candidates]
    if not create:
        existing = _first_existing_root(resolved_candidates)
        if existing is not None:
            return existing
        if resolved_candidates:
            return resolved_candidates[0]
        raise RuntimeError("cannot resolve root for hongzhi-ai-kit")

    for base in candidates:
        try:
            base.mkdir(parents=True, exist_ok=True)
            if _is_accessible_dir(base, require_write=True):
                return base
        except OSError:
            continue
    raise RuntimeError("cannot resolve writable root for hongzhi-ai-kit")


def resolve_global_state_root(override_root: str | None = None, read_only: bool = False) -> Path:
    """
    Resolve global state root used by capability registry/index.

    Priority:
      1) ~/Library/Application Support/hongzhi-ai-kit/
      2) ~/.hongzhi-ai-kit/
      3) ~/.cache/hongzhi-ai-kit/
      4) /tmp/hongzhi-ai-kit/
    """
    candidates = []
    if override_root:
        candidates.append(Path(override_root).expanduser())
    candidates.extend(
        [
            Path.home() / "Library" / "Application Support" / "hongzhi-ai-kit",
            Path.home() / ".hongzhi-ai-kit",
            Path.home() / ".cache" / "hongzhi-ai-kit",
            Path("/tmp") / "hongzhi-ai-kit",
        ]
    )
    return _first_writable_root(candidates, create=not read_only)


def resolve_workspace_root(override_root: str | None = None, read_only: bool = False) -> Path:
    """
    Resolve workspace root used for per-run artifacts.

    Priority:
      1) ~/Library/Caches/hongzhi-ai-kit/
      2) ~/.cache/hongzhi-ai-kit/
      3) /tmp/hongzhi-ai-kit/
    """
    candidates = []
    if override_root:
        candidates.append(Path(override_root).expanduser())
    candidates.extend(
        [
            Path.home() / "Library" / "Caches" / "hongzhi-ai-kit",
            Path.home() / ".cache" / "hongzhi-ai-kit",
            Path("/tmp") / "hongzhi-ai-kit",
        ]
    )
    return _first_writable_root(candidates, create=not read_only)
