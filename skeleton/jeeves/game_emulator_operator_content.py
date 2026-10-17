"""Pinned local multi-file emulator bundle admission shared by qualification and training.

No runtime binary is executed: each member is hashed and materialized by the
existing isolated host. Individual callers retain independent source rights.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import stat

def operator_directory_content(root: Path, entrypoint: str):
    """Pin an explicit local data tree; return its existing bundle and bounded reader.

    No path supplied to a native worker comes from content. The existing host
    materializes these exact references in its own private directory first.
    """
    from skeleton.jeeves.game_emulator_catalog import (
        MAX_CONTENT_FILES,
        MAX_REFERENCED_BUNDLE_BYTES,
        MAX_REFERENCED_FILE_BYTES,
        MAX_STREAM_CHUNK_BYTES,
        GameContentBundle,
        GameContentReference,
        _content_name,
        _safe_path,
    )

    root = _safe_path(str(root.absolute()))
    if not root.is_dir():
        raise ValueError("Explicit operator content root must be an existing nonsymlink directory")
    entrypoint = _content_name(entrypoint)
    rows, observed, pending, total, directory_count = [], {}, [(root, 0)], 0, 0

    def identity(details):
        return (details.st_dev, details.st_ino, details.st_size, details.st_mtime_ns, details.st_ctime_ns)

    while pending:
        folder, depth = pending.pop()
        directory_count += 1
        if depth > 8 or directory_count > 96:
            raise ValueError("Operator content directory exceeds its bounded depth or directory count")
        with os.scandir(folder) as entries:
            for entry in entries:
                if entry.is_symlink():
                    raise ValueError("Operator content directory cannot contain symbolic links")
                if entry.is_dir(follow_symlinks=False):
                    pending.append((Path(entry.path), depth + 1))
                    if len(pending) > 96:
                        raise ValueError("Operator content directory count exceeds 96")
                    continue
                if not entry.is_file(follow_symlinks=False) or len(rows) >= MAX_CONTENT_FILES:
                    raise ValueError("Operator content requires at most 96 bounded regular files")
                path = _safe_path(entry.path)
                name = _content_name(path.relative_to(root).as_posix())
                fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))
                try:
                    before = os.fstat(fd)
                    if (
                        not stat.S_ISREG(before.st_mode)
                        or not 1 <= before.st_size <= MAX_REFERENCED_FILE_BYTES
                    ):
                        raise ValueError("Operator content file exceeds the 2 GiB regular-file bound")
                    total += before.st_size
                    if total > MAX_REFERENCED_BUNDLE_BYTES:
                        raise ValueError("Operator content bundle exceeds the 4 GiB bound")
                    hasher, prefix, size = hashlib.sha256(), bytearray(), 0
                    suffix = path.suffix.casefold()
                    head_bytes = (
                        65536
                        if suffix in {".cue", ".gdi", ".m3u", ".ccd", ".toc", ".mds"}
                        else 34816 if suffix == ".iso" else 124 if suffix == ".chd" else 0
                    )
                    with os.fdopen(os.dup(fd), "rb") as stream:
                        while chunk := stream.read(MAX_STREAM_CHUNK_BYTES):
                            size += len(chunk)
                            if size > before.st_size:
                                raise ValueError("Operator content file grew during identity capture")
                            hasher.update(chunk)
                            if len(prefix) < head_bytes:
                                prefix.extend(chunk[: head_bytes - len(prefix)])
                    after = os.fstat(fd)
                    final = path.stat(follow_symlinks=False)
                    if (
                        size != before.st_size
                        or identity(before) != identity(after)
                        or identity(after) != identity(final)
                    ):
                        raise ValueError("Operator content changed during its exact-byte identity capture")
                    rows.append({"name": name, "sha256": hasher.hexdigest(), "size_bytes": size})
                    observed[name] = (path, identity(after), bytes(prefix))
                finally:
                    os.close(fd)
    rows.sort(key=lambda row: row["name"])
    source_digest = hashlib.sha256(
        json.dumps(
            {"entrypoint": entrypoint, "files": rows},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    references = {
        row["name"]: GameContentReference(
            row["name"],
            row["size_bytes"],
            row["sha256"],
            f"operator-local://{source_digest}/{index}",
            observed[row["name"]][2],
        )
        for index, row in enumerate(rows)
    }
    bundle = GameContentBundle(entrypoint, references, source_digest)

    def reader(reference):
        if not isinstance(reference, GameContentReference) or references.get(reference.name) != reference:
            raise ValueError("Operator content reader accepts only this exact pinned bundle")
        path, expected, _ = observed[reference.name]
        _safe_path(str(path))
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))
        try:
            if identity(os.fstat(fd)) != expected:
                raise ValueError("Operator content identity changed before native materialization")
            with os.fdopen(os.dup(fd), "rb") as stream:
                while chunk := stream.read(MAX_STREAM_CHUNK_BYTES):
                    yield chunk
            if identity(os.fstat(fd)) != expected or identity(path.stat(follow_symlinks=False)) != expected:
                raise ValueError("Operator content identity changed during native materialization")
        finally:
            os.close(fd)

    return bundle, reader

