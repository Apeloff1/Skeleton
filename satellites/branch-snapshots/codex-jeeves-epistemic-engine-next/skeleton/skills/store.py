"""Atomic, versioned filesystem store for skills."""
from __future__ import annotations
from pathlib import Path
from typing import Any
import json
import os
import tempfile
from .manifest import SkillManifest, SkillState

class SkillStore:
    def __init__(self, root: str | Path = ".skills") -> None:
        self.root = Path(root)

    def _dir(self, name: str) -> Path:
        if not name or name in {".", ".."} or "/" in name or "\\" in name:
            raise ValueError("invalid skill name")
        return self.root / name

    def save(self, manifest: SkillManifest, state: SkillState | None = None) -> Path:
        d = self._dir(manifest.name); d.mkdir(parents=True, exist_ok=True)
        self._atomic(d / "manifest.json", manifest.dumps())
        if state is not None: self._atomic(d / "state.json", json.dumps(state.to_dict(), indent=2, sort_keys=True))
        return d

    def load(self, name: str) -> tuple[SkillManifest, SkillState]:
        d = self._dir(name)
        manifest = SkillManifest.loads((d / "manifest.json").read_text(encoding="utf-8"))
        state_path = d / "state.json"
        state = SkillState(**json.loads(state_path.read_text(encoding="utf-8"))) if state_path.exists() else SkillState()
        return manifest, state

    @staticmethod
    def _atomic(path: Path, text: str) -> None:
        fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent), text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text); f.flush(); os.fsync(f.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
