"""Shared path containment helpers. Use these instead of raw Path joins."""
from __future__ import annotations
from pathlib import Path

def safe_join(root: Path, *parts: str) -> Path:
    """Join parts under root and prove the result stays inside root.
    Raises ValueError if the path would escape.
    """
    root_resolved = root.resolve()
    candidate = root_resolved
    for part in parts:
        if not isinstance(part, str) or not part or part in (".", "..") or "/" in part or "\\" in part:
            raise ValueError("invalid path segment")
        candidate = candidate / part
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError("path escapes root") from exc
    root_str = str(root_resolved)
    if not str(candidate).startswith(root_str):
        raise ValueError("path escapes root")
    return candidate

def safe_filename(name: str) -> str:
    """Return a filename that contains only safe characters."""
    if not isinstance(name, str) or not name:
        raise ValueError("invalid filename")
    cleaned = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)
    if not cleaned or cleaned in (".", ".."):
        raise ValueError("invalid filename")
    return cleaned[:128]
