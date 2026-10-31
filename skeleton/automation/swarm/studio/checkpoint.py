"""Durable studio checkpoints.

Wave manifests store path hashes, not a fresh copy of every file. Blob bytes
are written once. The manifest is replaced atomically: write a temp file,
fsync it, ``os.replace`` it, then fsync the directory.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path

CHECKPOINT_SCHEMA = "skeleton.studio.checkpoint.v1"
MAX_FILES = 400
MAX_FILE_BYTES = 1_000_000


class CheckpointError(ValueError):
    """A checkpoint could not be stored or restored."""


def checkpoint_paths(workspace: Path) -> tuple[Path, Path]:
    root = workspace / ".studio"
    return root / "checkpoint.json", root / "blobs"


def capture_tree(workspace: Path) -> dict[str, bytes]:
    """Read workspace files, skipping the checkpoint store itself."""
    found: dict[str, bytes] = {}
    if not workspace.exists():
        return found
    for path in sorted(workspace.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(workspace).as_posix()
        if relative == ".studio" or relative.startswith(".studio/"):
            continue
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            raise CheckpointError(f"{relative} exceeds the checkpoint byte cap")
        found[relative] = path.read_bytes()
        if len(found) > MAX_FILES:
            raise CheckpointError("workspace exceeds the checkpoint file cap")
    return found


def store_blobs(workspace: Path, files: Mapping[str, bytes]) -> dict[str, str]:
    """Write each distinct payload once and return path → sha256."""
    _manifest, blob_root = checkpoint_paths(workspace)
    blob_root.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    for relative, payload in files.items():
        digest = hashlib.sha256(payload).hexdigest()
        destination = blob_root / digest
        if not destination.is_file():
            _atomic_write(destination, payload)
        hashes[relative] = digest
    return hashes


def save_manifest(workspace: Path, manifest: Mapping[str, object]) -> None:
    path, _blobs = checkpoint_paths(workspace)
    payload = dict(manifest)
    payload["schema_version"] = CHECKPOINT_SCHEMA
    encoded = json.dumps(payload, sort_keys=True, indent=2).encode("utf-8")
    _atomic_write(path, encoded)


def load_manifest(workspace: Path) -> dict[str, object]:
    path, _blobs = checkpoint_paths(workspace)
    if not path.is_file():
        raise CheckpointError("checkpoint is missing")
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CheckpointError("checkpoint is not json") from exc
    if not isinstance(loaded, dict) or loaded.get("schema_version") != CHECKPOINT_SCHEMA:
        raise CheckpointError("unsupported checkpoint schema")
    return loaded


def materialize(workspace: Path, hashes: Mapping[str, str]) -> None:
    """Overwrite tracked files from blobs and delete files the snapshot does not have."""
    _manifest, blob_root = checkpoint_paths(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    current = capture_tree(workspace)
    for relative, digest in hashes.items():
        _require_relative(relative)
        blob = blob_root / str(digest)
        if not blob.is_file():
            raise CheckpointError(f"missing blob for {relative}")
        _atomic_write(workspace / relative, blob.read_bytes())
    for relative in current:
        if relative not in hashes:
            _unlink(workspace, relative)
    _prune_empty(workspace)


def _require_relative(relative: str) -> None:
    parts = Path(relative).parts
    if not relative or relative.startswith("/") or ".." in parts or Path(relative).is_absolute():
        raise CheckpointError(f"unsafe checkpoint path {relative}")


def _unlink(workspace: Path, relative: str) -> None:
    _require_relative(relative)
    path = workspace / relative
    if path.is_file() and not path.is_symlink():
        path.unlink()


def _prune_empty(workspace: Path) -> None:
    directories = sorted(
        (path for path in workspace.rglob("*") if path.is_dir() and path.name != ".studio" and ".studio" not in path.parts),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for directory in directories:
        try:
            directory.rmdir()
        except OSError:
            continue


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    directory = os.open(path.parent, flags)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
