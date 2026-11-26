"""Safe, content-addressed Godot text project materialization."""
from __future__ import annotations

import json
import os
import re
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


_PORTABLE_SEGMENT = re.compile(r"[A-Za-z0-9_.-]{1,120}\Z", re.ASCII)
_MAX_PORTABLE_PATH = 240


def _validate(files: Mapping[str, str]) -> dict[str, str]:
    """Admit one portable tree before any hash, archive, or disk publication.

    Match the API/Expo portable source path semantics even for CLI-only
    projection. Reject file/directory collisions and case aliases at *every*
    path component, not merely the full file name.
    """
    if not isinstance(files, Mapping):
        raise ValueError("Godot files must be a mapping")
    if len(files) > MAX_PROJECT_FILES:
        raise ValueError("generated project file count exceeds source budget")
    checked: dict[str, str] = {}
    leaves: set[str] = set()
    directories: dict[str, str] = {}
    for name, body in files.items():
        if type(name) is not str or not name or len(name) > _MAX_PORTABLE_PATH:
            raise ValueError("invalid generated source path")
        parts = name.split("/")
        if (PurePosixPath(name).is_absolute()
                or any(not _PORTABLE_SEGMENT.fullmatch(part)
                       or part.startswith(".") or part.endswith(".")
                       or part.split(".")[0].casefold() in _DEVICES for part in parts)):
            raise ValueError(f"unsafe generated source path: {name!r}")
        folded = name.casefold()
        if folded in leaves or folded in directories or folded in _INTERNAL:
            raise ValueError(f"ambiguous or reserved generated path: {name!r}")
        for depth in range(1, len(parts)):
            prefix = "/".join(parts[:depth])
            alias = prefix.casefold()
            if (alias in leaves or alias in _INTERNAL
                    or (alias in directories and directories[alias] != prefix)):
                raise ValueError(f"ambiguous generated directory: {prefix!r}")
            directories[alias] = prefix
        if type(body) is not str:
            raise ValueError(f"source must be text: {name!r}")
        # Validate Unicode in fixed chunks, avoiding a full extra encoded copy.
        try:
            for offset in range(0, len(body), 65536):
                body[offset:offset + 65536].encode("utf-8", errors="strict")
        except UnicodeError:
            raise ValueError(f"invalid generated source encoding: {name!r}") from None
        checked[name] = body
        leaves.add(folded)
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
