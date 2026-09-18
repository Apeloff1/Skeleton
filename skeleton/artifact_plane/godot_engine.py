"""Compatibility alias: godot_engine.binary.locate()."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from skeleton.artifact_plane.godot_locate import locate as _locate


class binary:
    @staticmethod
    def locate(root: str | Path | None = None) -> dict[str, Any]:
        return _locate(root)
