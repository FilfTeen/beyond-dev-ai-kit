"""Path resolution helpers for workspace and global capability state."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable


def _first_writable_root(candidates: Iterable[Path]) -> Path:
    for base in candidates:
        try:
            base.mkdir(parents=True, exist_ok=True)
            test_file = base / ".write_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink()
            return base
        except OSError:
            continue
    raise RuntimeError("cannot resolve writable root for hongzhi-ai-kit")


def resolve_global_state_root(override_root: str | None = None) -> Path:
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
    return _first_writable_root(candidates)


def resolve_workspace_root(override_root: str | None = None) -> Path:
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
    return _first_writable_root(candidates)

