"""Safe, content-addressed Godot text project materialization."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Dict, Mapping


class ProjectExistsError(FileExistsError):
    pass


_INTERNAL = {"forge_manifest.json", "context_ledger.json", "context_tensor.json", "build_report.md"}
_DEVICES = {"con", "nul", "aux", "prn", "conin$", "conout$"} | {
    f"{prefix}{i}" for prefix in ("com", "lpt") for i in "123456789¹²³"
}
MAX_PROJECT_FILES = 500_000
MAX_PROJECT_PATH_CHARS = 4096
MAX_PROJECT_TEXT_CHARS = 100 * 1024 * 1024


def _validate(files: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(files, Mapping):
        raise ValueError("Godot files must be a mapping")
    if len(files) > MAX_PROJECT_FILES:
        raise ValueError("generated project file count exceeds source budget")
    checked: dict[str, str] = {}
    aliases: set[str] = set()
    directories: dict[str, str] = {}
    for index, (name, body) in enumerate(files.items()):
        if index >= MAX_PROJECT_FILES:
            raise ValueError("generated project file count exceeds source budget")
        if (type(name) is not str or not name
                or len(name) > MAX_PROJECT_PATH_CHARS
                or unicodedata.normalize("NFC", name) != name
                or any(c in '\\\\:<>|"*?' or unicodedata.category(c).startswith("C") for c in name)):
            raise ValueError("invalid generated source path")
        parts = name.split("/")
        if (PurePosixPath(name).is_absolute() or len(parts) > 64
                or any(p in ("", ".", "..") or p.rstrip(" .") != p
                       or len(p.encode("utf-8")) > 255
                       or p.split(".", 1)[0].rstrip(" ").casefold() in _DEVICES for p in parts)):
            raise ValueError("unsafe generated source path")
        alias = name.casefold()
        if alias in aliases or alias in directories or alias in _INTERNAL:
            raise ValueError("ambiguous or reserved generated path")
        for depth in range(1, len(parts)):
            prefix = "/".join(parts[:depth])
            folded = prefix.casefold()
            if (folded in aliases or folded in _INTERNAL
                    or (folded in directories and directories[folded] != prefix)):
                raise ValueError("ambiguous or reserved generated directory")
            directories[folded] = prefix
        if type(body) is not str:
            raise ValueError("source must be text")
        if len(body) > MAX_PROJECT_TEXT_CHARS:
            raise ValueError("generated source exceeds file text budget")
        checked[name] = body
        aliases.add(alias)
    if "project.godot" not in checked:
        raise ValueError("missing project.godot")
    return checked


def _is_link(path: Path) -> bool:
    junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(junction and junction())


def _check_existing(root: Path, paths: Mapping[str, str], overwrite: bool) -> None:
    if _is_link(root) or (root.exists() and not root.is_dir()):
        raise ValueError("unsafe destination directory")
    for name in (*paths, "FORGE_MANIFEST.json"):
        node = root
        for part in name.split("/"):
            node = node / part
            if _is_link(node):
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
    from skeleton.forge.source_manifest import source_manifest
    receipt = source_manifest(safe)
    manifest = {
        "root": str(root.resolve()), "files": sorted(safe), "count": len(safe),
        "sha256": receipt["files"], "source_sha256": receipt["sha256"],
        "meta": meta or {},
    }
    encoded = json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False)
    root.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{root.name}.forge-", dir=root.parent))
    try:
        for name, body in safe.items():
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("wb") as handle:
                for offset in range(0, len(body), 64 * 1024):
                    handle.write(body[offset:offset + 64 * 1024].encode("utf-8"))
        (stage / "FORGE_MANIFEST.json").write_bytes(encoded.encode("utf-8"))
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
