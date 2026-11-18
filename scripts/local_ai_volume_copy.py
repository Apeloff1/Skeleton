"""Offline, isolated, resumeless Docker state-volume byte archive worker.

This module is executed inside the already-built canonical Skeleton image.
It is *never* a MongoDB logical dump, SQLite online backup, Chroma snapshot,
atomic cross-volume backup, or application restore. Only explicit host-owned
cold-copy orchestration may invoke it, with network disabled, no credentials,
a read-only source mount and a private new destination.

Archive rows use streaming JSONL with a separate digest receipt; neither
source filenames nor Mongo documents appear in stdout. Files with symlinks,
hardlinks, special device types and unstable stat identities fail closed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path, PurePosixPath

SCHEMA = "skeleton.local-ai.docker.state-volume-byte-archive.v1"
MANIFEST = ".volume-files.jsonl"
RECEIPT = ".volume-receipt.json"
ROLES = frozenset(("mongo_data", "mongo_config", "backend_data",
                   "skeleton_data", "chroma_data"))
CHUNK = 4 * 1024 * 1024
MAX_ENTRIES = 5_000_000
MAX_FILE_BYTES = 16 * 1024 ** 4
MAX_TOTAL_BYTES = 32 * 1024 ** 4
MAX_PATH_BYTES = 4096


class VolumeCopyError(RuntimeError):
    """Physical volume copy/verification cannot establish exact byte custody."""


def _readable_private_root(root: Path) -> Path:
    if not root.is_dir() or root.is_symlink():
        raise VolumeCopyError("source or archive root unavailable")
    return root


def _name(path: Path) -> str:
    relative = path.as_posix()
    if (not relative or relative.startswith("/") or
            relative in (".", "..") or
            any(part in (".", "..", "") for part in PurePosixPath(relative).parts) or
            len(relative.encode("utf-8")) > MAX_PATH_BYTES or
            "\x00" in relative or
            relative in (MANIFEST, RECEIPT)):
        raise VolumeCopyError("volume file path is not safely representable")
    return relative


def _walk(source: Path, *, allow_metadata: bool = False) -> list[Path]:
    """Bound every path and inode; cannot follow links into host data."""
    paths: list[Path] = []
    for parent, dirs, files in os.walk(source, topdown=True, followlinks=False):
        dirs.sort()
        files.sort()
        for name in dirs:
            current = Path(parent) / name
            st = current.lstat()
            if not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode):
                raise VolumeCopyError("volume contains a linked or special directory")
            _name(current.relative_to(source))
        for name in files:
            current = Path(parent) / name
            st = current.lstat()
            if (not stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode)
                    or st.st_nlink != 1 or st.st_size < 0
                    or st.st_size > MAX_FILE_BYTES):
                raise VolumeCopyError("volume contains a linked or non-regular file")
            relative = current.relative_to(source)
            if not (allow_metadata and relative.as_posix() in (MANIFEST, RECEIPT)):
                _name(relative)
            paths.append(relative)
            if len(paths) > MAX_ENTRIES:
                raise VolumeCopyError("volume file count exceeds bounded worker inventory")
    # In-memory path pointers, not file bytes. Streaming per file avoids volume
    # RAM explosions but millions of path pointers still require worker sizing.
    return paths


def _digest_file(path: Path, *, expected_size: int | None = None) -> tuple[str, int]:
    start = path.lstat()
    if (not stat.S_ISREG(start.st_mode) or start.st_nlink != 1 or
            start.st_size < 0 or start.st_size > MAX_FILE_BYTES):
        raise VolumeCopyError("archive contains unadmitted source file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    h = hashlib.sha256()
    total = 0
    with os.fdopen(os.open(path, flags), "rb", buffering=0) as src:
        opened = os.fstat(src.fileno())
        if opened.st_ino != start.st_ino or opened.st_dev != start.st_dev:
            raise VolumeCopyError("volume inode identity changed")
        while True:
            block = src.read(CHUNK)
            if not block:
                break
            total += len(block)
            if total > MAX_FILE_BYTES:
                raise VolumeCopyError("file exceeded copy byte budget")
            h.update(block)
    end = path.lstat()
    if (end.st_ino, end.st_dev, end.st_size, end.st_mtime_ns, end.st_ctime_ns) != (
            start.st_ino, start.st_dev, start.st_size,
            start.st_mtime_ns, start.st_ctime_ns) or total != start.st_size:
        raise VolumeCopyError("volume source mutated during byte read")
    if expected_size is not None and expected_size != total:
        raise VolumeCopyError("independent volume archive size drift")
    return h.hexdigest(), total


def _copy_one(src: Path, target: Path) -> tuple[str, int]:
    start = src.lstat()
    if (not stat.S_ISREG(start.st_mode) or start.st_nlink != 1 or
            start.st_size > MAX_FILE_BYTES):
        raise VolumeCopyError("cannot copy nonregular volume bytes")
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    outflags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    h = hashlib.sha256()
    total = 0
    with os.fdopen(os.open(src, flags), "rb", buffering=0) as fsrc:
        opened = os.fstat(fsrc.fileno())
        if (opened.st_ino, opened.st_dev) != (start.st_ino, start.st_dev):
            raise VolumeCopyError("volume file changed between scan and open")
        with os.fdopen(os.open(target, outflags, 0o600), "wb", buffering=0) as fdst:
            while True:
                block = fsrc.read(CHUNK)
                if not block:
                    break
                total += len(block)
                if total > MAX_FILE_BYTES:
                    raise VolumeCopyError("volume file exceeded byte limit")
                h.update(block)
                fdst.write(block)
            os.fsync(fdst.fileno())
    end = src.lstat()
    if (end.st_dev, end.st_ino, end.st_size, end.st_mtime_ns, end.st_ctime_ns) != (
            start.st_dev, start.st_ino, start.st_size,
            start.st_mtime_ns, start.st_ctime_ns) or total != start.st_size:
        raise VolumeCopyError("source changed while copying offline archive")
    return h.hexdigest(), total


def _jsonline(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, ensure_ascii=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _receipt(volume: str, *, count: int, total: int, digest: str) -> dict:
    return {
        "schema": SCHEMA,
        "volume_role": volume,
        "files": count,
        "bytes": total,
        "manifest_sha256": digest,
        "status": "volume_bytes_copied_not_database_consistency_qualified",
        "cross_store_snapshot_atomic": False,
        "application_restore_qualified": False,
        "protected_jeeves_qualified": False,
    }


def _write_receipt(target: Path, receipt: dict) -> None:
    name = target / RECEIPT
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(name, flags, 0o600), "wb") as stream:
        stream.write(_jsonline(receipt))
        stream.flush()
        os.fsync(stream.fileno())


def copy_volume(volume: str, source: Path, destination: Path) -> dict:
    if volume not in ROLES:
        raise VolumeCopyError("unsupported Docker application volume role")
    source = _readable_private_root(source)
    target_root = _readable_private_root(destination)
    target = target_root / volume
    if target.exists() or target.is_symlink() or source == target:
        raise VolumeCopyError("archive copy destination must not exist")
    paths = _walk(source)  # Fail before creating new archive subdirectory.
    target.mkdir(mode=0o700)
    count, total = 0, 0
    stream_name = target / MANIFEST
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(stream_name, flags, 0o600), "wb", buffering=0) as index:
        for item in paths:
            path = _name(item)
            digest, size = _copy_one(source / item, target / item)
            total += size
            count += 1
            if total > MAX_TOTAL_BYTES:
                raise VolumeCopyError("volume exceeds cumulative copy budget")
            index.write(_jsonline({"path": path, "sha256": digest, "bytes": size}))
        os.fsync(index.fileno())
    manifest_sha, _ = _digest_file(stream_name)
    receipt = _receipt(volume, count=count, total=total, digest=manifest_sha)
    _write_receipt(target, receipt)  # Last: partial copies never qualify.
    verified = verify_volume(volume, destination)
    if verified != receipt:
        raise VolumeCopyError("copied volume failed independent byte rehash")
    return receipt


def verify_volume(volume: str, destination: Path) -> dict:
    if volume not in ROLES:
        raise VolumeCopyError("unsupported application state archive role")
    target = _readable_private_root(destination) / volume
    _readable_private_root(target)
    manifest = target / MANIFEST
    record = target / RECEIPT
    for file in (manifest, record):
        if file.is_symlink() or not file.is_file() or file.stat().st_nlink != 1:
            raise VolumeCopyError("archive manifest has unsafe file identity")
    if record.stat().st_size > 8192:
        raise VolumeCopyError("archive receipt exceeds bounded size")
    try:
        receipt = json.loads(record.read_bytes())
    except (ValueError, UnicodeError, OSError):
        raise VolumeCopyError("volume receipt invalid") from None
    if not isinstance(receipt, dict) or set(receipt) != set(_receipt(volume, count=0, total=0, digest="0"*64)):
        raise VolumeCopyError("archive receipt contains unsupported fields")
    if (receipt.get("schema") != SCHEMA or receipt.get("volume_role") != volume
            or receipt.get("status") != "volume_bytes_copied_not_database_consistency_qualified"
            or any(receipt.get(key) is not False for key in (
                "cross_store_snapshot_atomic", "application_restore_qualified",
                "protected_jeeves_qualified",
            )) or type(receipt.get("files")) is not int or
            not 0 <= receipt["files"] <= MAX_ENTRIES or
            type(receipt.get("bytes")) is not int or
            not 0 <= receipt["bytes"] <= MAX_TOTAL_BYTES):
        raise VolumeCopyError("archive receipt has unqualified recovery authority")
    actual_manifest, _ = _digest_file(manifest)
    if receipt.get("manifest_sha256") != actual_manifest:
        raise VolumeCopyError("archive manifest digest mismatch")
    count, total = 0, 0
    expected = {MANIFEST, RECEIPT}
    with manifest.open("rb", buffering=CHUNK) as source:
        for line in source:
            if len(line) > MAX_PATH_BYTES * 3 or not line.endswith(b"\n"):
                raise VolumeCopyError("archive index line outside bounds")
            try:
                data = json.loads(line)
                if not isinstance(data, dict) or set(data) != {"path", "sha256", "bytes"}:
                    raise ValueError("index shape")
                relative = _name(PurePosixPath(data["path"]))
                if data["path"] != relative:
                    raise ValueError("noncanonical relative path")
                digest = data["sha256"]
                size = data["bytes"]
            except (TypeError, ValueError, UnicodeError):
                raise VolumeCopyError("archive contains invalid file inventory") from None
            if (relative in expected or type(size) is not int or
                    not 0 <= size <= MAX_FILE_BYTES or
                    not isinstance(digest, str) or len(digest) != 64
                    or any(x not in "0123456789abcdef" for x in digest)):
                raise VolumeCopyError("archive contains duplicated or invalid file identity")
            expected.add(relative)
            seen, count_bytes = _digest_file(target / relative, expected_size=size)
            if seen != digest or count_bytes != size:
                raise VolumeCopyError("archive file bytes differ from manifest")
            count += 1
            total += size
            if count > MAX_ENTRIES or total > MAX_TOTAL_BYTES:
                raise VolumeCopyError("archive inventory count exceeded bounds")
    actual = {
        item.as_posix() if item.as_posix() in (MANIFEST, RECEIPT)
        else _name(item)
        for item in _walk(target, allow_metadata=True)
    }
    if expected != actual:
        raise VolumeCopyError("archive has missing or undeclared extra files")
    if receipt != _receipt(volume, count=count, total=total, digest=actual_manifest):
        raise VolumeCopyError("volume archive tally or authority differs")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("copy", "verify"))
    parser.add_argument("--role", choices=tuple(sorted(ROLES)), required=True)
    parser.add_argument("--source", type=Path, default=Path("/source"))
    parser.add_argument("--archive", type=Path, default=Path("/archive"))
    args = parser.parse_args(argv)
    try:
        result = (copy_volume(args.role, args.source, args.archive)
                  if args.action == "copy"
                  else verify_volume(args.role, args.archive))
        print(json.dumps({"ok": True, **result}, sort_keys=True))
        return 0
    except (VolumeCopyError, ValueError, OSError, UnicodeError, TypeError):
        print(json.dumps({"ok": False, "error": "volume byte custody unavailable"}),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
