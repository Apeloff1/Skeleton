"""Host-authorized local multi-file media admission for comparative libretro studies.

Reuses the existing GameContentBundle and streaming GameContentReference
authority; never downloads content or reads entire multi-GiB files into RAM.
Pinned file lengths, SHA-256, exact CUE/GDI/M3U references and ISO/CHD magic
are validated by the canonical emulator materialization pipeline.
"""
from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .game_comparison_schema import ComparativeStudyError, digest
from .game_emulator_catalog import (
    GameContentBundle, GameContentReference,
    MAX_STREAM_CHUNK_BYTES,
)

MAX_LOCAL_PATH_COMPONENTS = 24
MAX_PREFIX_BYTES = 65536


def _open_no_symlink(path: str) -> int:
    """Open every path component without symlinks to prevent parent traversal."""
    if (type(path) is not str or not path.startswith("/") or "\x00" in path
        or len(path.encode("utf-8")) > 2048):
        raise ComparativeStudyError("Local game-media path is not an absolute bounded path")
    parts = path.split("/")[1:]
    if (not 1 <= len(parts) <= MAX_LOCAL_PATH_COMPONENTS
        or any(part in ("", ".", "..") for part in parts)):
        raise ComparativeStudyError("Game-media paths require absolute canonical components")
    opened = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in parts[:-1]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                dir_fd=opened,
            )
            os.close(opened)
            opened = child
        result = os.open(
            parts[-1], os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
            dir_fd=opened,
        )
        return result
    finally:
        os.close(opened)


def _snapshot(fd: int, size: int, *, path: str) -> tuple[int,int,int,int]:
    x = os.fstat(fd)
    if not stat.S_ISREG(x.st_mode) or x.st_size != size or size <= 0:
        raise ComparativeStudyError("Local game media is not the expected regular-file size")
    return x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns


def _prefix_size(name: str, size: int) -> int:
    suffix=Path(name).suffix.casefold()
    if suffix in (".cue", ".gdi", ".m3u"):
        if size > MAX_PREFIX_BYTES:
            raise ComparativeStudyError("Disc playlist/descriptor exceeds its 64-KiB bound")
        return size
    if suffix == ".iso":
        return min(size,17*2048+7)
    if suffix == ".chd":
        return min(size,124)
    return 0


class LocalComparativeMedia:
    """Immutable bound local artifact reader for a single game study session."""

    def __init__(self, manifest: Mapping[str, Any]):
        if not isinstance(manifest, dict) or set(manifest) != {"entrypoint", "files"}:
            raise ComparativeStudyError("Multi-file game requires a normalized checked study bundle")
        self._sources: dict[str, tuple[str,int,tuple[int,int,int,int]]] = {}
        refs={}
        for row in manifest["files"]:
            path, name, size = row["path"], row["name"], row["size_bytes"]
            identity = "local-study:" + digest([path, name, size, row["sha256"]])
            fd = _open_no_symlink(path)
            try:
                snap = _snapshot(fd, size, path=path)
                prefix_length = _prefix_size(name,size)
                prefix = os.read(fd,prefix_length) if prefix_length else b""
                if len(prefix) != prefix_length:
                    raise ComparativeStudyError("Disc header changed or was truncated while being read")
                if prefix_length == size and hashlib.sha256(prefix).hexdigest() != row["sha256"]:
                    raise ComparativeStudyError("Disc playlist/descriptor bytes differ from pinned SHA-256")
                if _snapshot(fd,size,path=path) != snap:
                    raise ComparativeStudyError("Disc metadata mutated during header admission")
            finally:
                os.close(fd)
            self._sources[identity]=(path,size,snap)
            refs[name]=GameContentReference(
                name,size,row["sha256"],identity,prefix,
            )
        source_sha = digest([
            manifest["entrypoint"],
            [(name, ref.size_bytes, ref.sha256) for name,ref in sorted(refs.items())],
        ])
        self.bundle=GameContentBundle(manifest["entrypoint"],refs,source_sha)
        self.bundle_digest=self.bundle.bundle_digest

    def reader(self, ref: GameContentReference) -> Iterable[bytes]:
        source = self._sources.get(ref.artifact_ref)
        if source is None:
            raise ComparativeStudyError("Local media reference has no current authorized bound artifact")
        path,size,snapshot=source
        fd = _open_no_symlink(path)
        try:
            if _snapshot(fd,size,path=path) != snapshot:
                raise ComparativeStudyError("Disc data changed since manifest admission")
            remaining=size
            while remaining:
                chunk=os.read(fd,min(MAX_STREAM_CHUNK_BYTES,remaining))
                if not chunk:
                    raise ComparativeStudyError("Disc reader reached EOF before exact pinned byte count")
                remaining-=len(chunk)
                yield chunk
            if _snapshot(fd,size,path=path) != snapshot:
                raise ComparativeStudyError("Disc data changed while reading actual native source")
        finally:
            os.close(fd)


def prepare_comparison_media(game: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    """Return canonical create_emulator_environment kwargs and exact media lineage."""
    bundle=game.get("content_bundle")
    if bundle is None:
        from .game_comparison_studio import _source_file
        data,name=_source_file(game)
        return {"rom_source":data,"filename":name},game["source_sha256"]
    media=LocalComparativeMedia(bundle)
    return {"content":media.bundle,"reader":media.reader},media.bundle_digest
