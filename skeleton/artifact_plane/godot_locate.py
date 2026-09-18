"""Godot binary locator. found=0 must never raise at import or call."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from skeleton.artifact_plane.cards import plane_card

POINTER_NAMES = (
    "godot.pointer",
    "godot_engine.pointer",
    ".godot-engine.pointer",
)
CANDIDATE_RELATIVE = (
    "tools/godot/Godot",
    "tools/godot/godot",
    "third_party/godot/Godot",
    "backend/godot/Godot",
    "backend/godot/godot",
)


class GodotLocator:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else Path.cwd()

    def locate(self) -> dict[str, Any]:
        env = os.environ.get("SKELETON_GODOT_BIN")
        if env:
            path = Path(env)
            if path.is_file():
                return plane_card(
                    kind="godot-binary",
                    hit=1,
                    law="GB-9",
                    citation="docs/ARTIFACT_PLANE.md",
                    extra={"found": 1, "hint": "env:SKELETON_GODOT_BIN", "path": str(path)},
                )
        for relative in CANDIDATE_RELATIVE:
            path = self.root / relative
            if path.is_file():
                return plane_card(
                    kind="godot-binary",
                    hit=1,
                    law="GB-9",
                    citation="docs/ARTIFACT_PLANE.md",
                    extra={"found": 1, "hint": relative, "path": str(path)},
                )
        pointer = self._pointer()
        hint = "pointer:" + pointer if pointer else "missing-godot-binary"
        return plane_card(
            kind="godot-binary",
            hit=0,
            law="GB-9",
            citation="docs/ARTIFACT_PLANE.md",
            extra={"found": 0, "hint": hint},
        )

    def _pointer(self) -> str | None:
        for name in POINTER_NAMES:
            path = self.root / name
            if path.is_file():
                try:
                    text = path.read_text(encoding="utf-8").strip().splitlines()
                except OSError:
                    return name
                return text[0] if text else name
        return None


def locate(root: str | Path | None = None) -> dict[str, Any]:
    return GodotLocator(root).locate()
