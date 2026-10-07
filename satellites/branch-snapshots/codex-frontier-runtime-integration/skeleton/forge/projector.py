"""Write a materialised Godot tree to disk. No silent overwrite."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Mapping


class ProjectExistsError(FileExistsError):
    pass


def write_project(root: str | Path, files: Mapping[str, str], *,
                  overwrite: bool = False,
                  meta: Dict | None = None) -> Dict[str, object]:
    root = Path(root)
    if (root / "project.godot").exists() and not overwrite:
        raise ProjectExistsError(f"project already exists at {root}")
    root.mkdir(parents=True, exist_ok=True)
    written = []
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        written.append(rel)
    manifest = {
        "root": str(root.resolve()),
        "files": sorted(written),
        "count": len(written),
        "meta": meta or {},
    }
    (root / "FORGE_MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
