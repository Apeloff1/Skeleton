"""Safe, content-addressed Godot text project materialization."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Dict, Mapping


class ProjectExistsError(FileExistsError):
    pass


_INTERNAL = {"forge_manifest.json", "context_ledger.json", "context_tensor.json", "build_report.md"}
_DEVICES = {"con", "nul", "aux", "prn"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}


def _validate(files: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(files, Mapping):
        raise ValueError("Godot files must be a mapping")
    checked: dict[str, str] = {}
    aliases: set[str] = set()
    for name, body in files.items():
        if not isinstance(name, str) or not name or "\\" in name or any(ord(c) < 32 for c in name):
            raise ValueError("invalid generated source path")
        parts = name.split("/")
        if (PurePosixPath(name).is_absolute() or ":" in name
                or any(p in ("", ".", "..") or p.rstrip(" .") != p
                       or p.split(".")[0].casefold() in _DEVICES for p in parts)):
            raise ValueError(f"unsafe generated source path: {name!r}")
        if name.casefold() in aliases or name.casefold() in _INTERNAL:
            raise ValueError(f"ambiguous or reserved generated path: {name!r}")
        if not isinstance(body, str):
            raise ValueError(f"source must be text: {name!r}")
        checked[name] = body
        aliases.add(name.casefold())
    if "project.godot" not in checked:
        raise ValueError("missing project.godot")
    return checked


def _check_existing(root: Path, paths: Mapping[str, str], overwrite: bool) -> None:
    if root.is_symlink() or (root.exists() and not root.is_dir()):
        raise ValueError("unsafe destination directory")
    for name in (*paths, "FORGE_MANIFEST.json"):
        node = root
        for part in name.split("/"):
            node = node / part
            if node.is_symlink():
                raise ValueError(f"symlink in generated destination: {name}")
        if node.exists() and not overwrite:
            raise ProjectExistsError(f"generated file already exists: {name}")
    if (root / "project.godot").exists() and not overwrite:
        raise ProjectExistsError(f"project already exists at {root}")


def write_project(root: str | Path, files: Mapping[str, str], *,
                  overwrite: bool = False,
                  meta: Dict | None = None) -> Dict[str, object]:
    root = Path(root)
    if root.name in ("", ".", ".."):
        raise ValueError("project destination must be named")
    safe = _validate(files)  # whole-manifest validation before side effects
    _check_existing(root, safe, overwrite)
    manifest = {
        "root": str(root.resolve()), "files": sorted(safe), "count": len(safe),
        "sha256": {k: hashlib.sha256(v.encode("utf-8")).hexdigest()
                   for k, v in sorted(safe.items())},
        "meta": meta or {},
    }
    encoded = json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False)
    root.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{root.name}.forge-", dir=root.parent))
    try:
        for name, body in safe.items():
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        (stage / "FORGE_MANIFEST.json").write_text(encoded, encoding="utf-8")
        if not root.exists():
            os.replace(stage, root)  # publish new project atomically
            return manifest
        _check_existing(root, safe, overwrite)  # revalidate before publication
        for name in (*safe, "FORGE_MANIFEST.json"):
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(stage / name, target)
        return manifest
    finally:
        if stage.exists():
            shutil.rmtree(stage)
