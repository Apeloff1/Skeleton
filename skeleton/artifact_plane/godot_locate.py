"""Godot binary locator with fail-closed artifact identity verification."""

from __future__ import annotations

import hashlib
import json
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
    "backend/godot",
    "tools/godot/Godot",
    "tools/godot/godot",
    "third_party/godot/Godot",
    "backend/godot/Godot",
    "backend/godot/godot",
)
_ARTIFACT_MANIFEST = Path("backend") / "godot.artifact.json"
_HASH_CHUNK_BYTES = 1024 * 1024


class GodotLocator:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else Path.cwd()

    def locate(self) -> dict[str, Any]:
        manifest = self._manifest()
        env = os.environ.get("SKELETON_GODOT_BIN") or os.environ.get("GODOT_BINARY")
        if env:
            path = Path(env)
            if path.is_file():
                hint = (
                    "env:SKELETON_GODOT_BIN"
                    if os.environ.get("SKELETON_GODOT_BIN")
                    else "env:GODOT_BINARY"
                )
                card = self._verified_card(path, hint, manifest)
                if card is not None:
                    return card
        for relative in CANDIDATE_RELATIVE:
            path = self.root / relative
            if path.is_file():
                card = self._verified_card(path, relative, manifest)
                if card is not None:
                    return card
        pointer = self._pointer()
        hint = "pointer:" + pointer if pointer else "missing-godot-binary"
        return plane_card(
            kind="godot-binary",
            hit=0,
            law="GB-9",
            citation="docs/ARTIFACT_PLANE.md",
            extra={"found": 0, "hint": hint},
        )

    def _verified_card(
        self,
        path: Path,
        hint: str,
        manifest: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Return an admitted card only when the candidate matches the manifest."""
        if manifest is None:
            return None
        expected = manifest.get("sha256")
        if not isinstance(expected, str) or len(expected) != 64:
            return None
        try:
            int(expected, 16)
        except ValueError:
            return None

        expected_size = manifest.get("bytes", manifest.get("approx_bytes"))
        if expected_size is not None:
            if isinstance(expected_size, bool) or not isinstance(expected_size, int) or expected_size < 0:
                return None
            try:
                if path.stat().st_size != expected_size:
                    return None
            except OSError:
                return None

        digest = hashlib.sha256()
        try:
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(_HASH_CHUNK_BYTES), b""):
                    digest.update(chunk)
        except OSError:
            return None
        actual = digest.hexdigest()
        if actual.lower() != expected.lower():
            return None
        return plane_card(
            kind="godot-binary",
            hit=1,
            law="GB-9",
            citation="docs/ARTIFACT_PLANE.md",
            extra={
                "found": 1,
                "hint": hint,
                "path": str(path),
                "sha256": actual,
            },
        )

    def _manifest(self) -> dict[str, Any] | None:
        path = self.root / _ARTIFACT_MANIFEST
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def _pointer(self) -> str | None:
        for name in POINTER_NAMES:
            path = self.root / name
            if path.is_file():
                try:
                    text = path.read_text(encoding="utf-8").strip().splitlines()
                except OSError:
                    return name
                return text[0] if text else name
        artifact = self.root / _ARTIFACT_MANIFEST
        if artifact.is_file():
            try:
                data = json.loads(artifact.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return str(_ARTIFACT_MANIFEST)
            if isinstance(data, dict):
                return str(data.get("source") or data.get("hint") or _ARTIFACT_MANIFEST)
            return str(_ARTIFACT_MANIFEST)
        return None


def locate(root: str | Path | None = None) -> dict[str, Any]:
    return GodotLocator(root).locate()
