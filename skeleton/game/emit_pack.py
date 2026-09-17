"""Validate an emit-pack tree as names only. No Godot binary. No vendor dump."""

from __future__ import annotations

from typing import Any, Iterable


REQUIRED = (
    "project.godot",
    "world.json",
    "world.gd",
    "world.tscn",
    "player.gd",
    "jeeves/",
    "heat/",
    "forge/",
    "extract/",
    "reports/build_report.md",
    "data/spec.json",
)
FORBIDDEN = ("backend/godot", "godot.exe", "__pycache__", ".env")
MAX_FILES = 64


class EmitPackError(ValueError):
    """Emit pack contract violation."""


def validate_emit(files: Iterable[str] | None) -> dict[str, Any]:
    names = [str(item).replace("\\", "/").strip() for item in (files or [])]
    if any(not name for name in names):
        raise EmitPackError("empty path")
    if len(names) > MAX_FILES:
        raise EmitPackError("too many files")
    lowered = [name.lower() for name in names]
    for banned in FORBIDDEN:
        if any(banned in name for name in lowered):
            raise EmitPackError(f"forbidden path: {banned}")
    missing = [item for item in REQUIRED if item not in names]
    return {
        "kind": "gamefile-ops",
        "files": names,
        "missing": missing,
        "valid": 0 if missing else 1,
        "fixes": 0,
        "godot_binary": 0,
        "stored_prose": 0,
    }


def default_tree() -> list[str]:
    return list(REQUIRED)
