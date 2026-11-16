"""Authenticate every GGUF shard without loading model weights or running tools.

POSIX descriptor-anchored operator preflight. A receipt is not runtime
activation: canonical launcher admits only explicit pinned bundles.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Sequence

from collections.abc import Callable

_NAME = re.compile(r"(.{1,180})-00001-of-([0-9]{5})\.gguf")
_HEX = re.compile(r"[0-9a-f]{64}")
_MAX_SHARDS = 128
_MAX_BYTES = 1024**4


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_nlink)


def _open_directory(path: Path) -> int:
    if (os.name != "posix" or not hasattr(os, "O_NOFOLLOW")
            or not hasattr(os, "O_DIRECTORY") or os.open not in os.supports_dir_fd):
        raise OSError("descriptor-anchored shard custody is unavailable")
    parts = path.parts
    fd = os.open(parts[0], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _open_file(directory: int, name: str) -> int:
    return os.open(name, os.O_RDONLY | os.O_NOFOLLOW
                   | getattr(os, "O_NONBLOCK", 0), dir_fd=directory)


def _read_shard(directory, name, pin, remaining, *, interrupt=None, private=False):
    from .llama_cpp import _inspect_gguf_stream, _serving_metadata
    fd = _open_file(directory, name)
    with os.fdopen(fd, "rb") as stream:
        initial = os.fstat(stream.fileno())
        if not stat.S_ISREG(initial.st_mode) or initial.st_nlink != 1:
            raise ValueError("shard must be a regular, non-hardlinked file")
        if private and (initial.st_uid != os.geteuid() or initial.st_mode & 0o022):
            raise PermissionError("native shard must be owned and not group/other writable")
        if not 24 <= initial.st_size <= remaining:
            raise ValueError("shard exceeds remaining bundle byte budget")
        header = _inspect_gguf_stream(stream)
        metadata = _serving_metadata(Path(name), header, stream=stream)
        if not metadata.is_split:
            raise ValueError("shard lacks multi-file GGUF metadata")
        stream.seek(0)
        digest = hashlib.sha256()
        size = 0
        while True:
            if interrupt is not None:
                interrupt()
            chunk = stream.read(min(1024 * 1024, remaining - size + 1))
            if not chunk:
                break
            size += len(chunk)
            if size > remaining:
                raise ValueError("shard exceeded byte budget while reading")
            digest.update(chunk)
        identity = _identity(initial)
        if size != initial.st_size or _identity(os.fstat(stream.fileno())) != identity:
            raise OSError("shard changed during verification")
        if digest.hexdigest() != pin:
            raise ValueError("shard SHA-256 mismatch")
        return header, metadata, identity


def audit_bundle(first: Path, pins: Sequence[str], *, max_bytes: int,
                 private: bool = False, interrupt: Callable[[], None] | None = None) -> dict:
    if type(max_bytes) is not int or not 1 <= max_bytes <= _MAX_BYTES:
        raise ValueError("bundle byte budget must be within 1 TiB")
    if not isinstance(first, Path) or ".." in first.parts:
        raise ValueError("explicit first-shard path without traversal required")
    first = Path(os.path.abspath(first.expanduser()))
    match = _NAME.fullmatch(first.name)
    if not match:
        raise ValueError("first shard requires canonical -00001-of-NNNNN.gguf name")
    prefix, count_text = match.groups()
    count = int(count_text)
    if not 2 <= count <= _MAX_SHARDS or len(pins) != count:
        raise ValueError("each of 2–128 shards requires an ordered digest pin")
    if any(not isinstance(pin, str) or not _HEX.fullmatch(pin) for pin in pins):
        raise ValueError("all shard pins must be lowercase SHA-256")
    if len(set(pins)) != count:
        raise ValueError("duplicate shard digest")
    directory = _open_directory(first.parent)
    try:
        parent_identity = os.fstat(directory)
        if private and (parent_identity.st_uid != os.geteuid() or parent_identity.st_mode & 0o077):
            raise PermissionError("native split GGUF requires an owner-private directory")
        observed = []
        rows = []
        used = tensors = 0
        total_tensors = version = None
        for index, pin in enumerate(pins):
            name = f"{prefix}-{index+1:05d}-of-{count:05d}.gguf"
            header, metadata, identity = _read_shard(directory, name, pin, max_bytes - used, interrupt=interrupt, private=private)
            if (metadata.split_number != index or metadata.split_count != count
                    or (total_tensors is not None and metadata.split_tensor_count != total_tensors)
                    or (version is not None and header.version != version)):
                raise ValueError("inconsistent shard index, count, tensor total or version")
            total_tensors = metadata.split_tensor_count
            version = header.version
            used += identity[2]
            tensors += header.tensor_count
            observed.append((name, identity))
            rows.append({"ordinal": index, "sha256": pin, "bytes": identity[2],
                         "tensor_count": header.tensor_count})
        if tensors != total_tensors:
            raise ValueError("combined shard tensor count does not match declared total")
        # Reopen the original directory by descriptor walk, then recheck
        # every component's file identity before publishing an audit receipt.
        current = _open_directory(first.parent)
        try:
            check = os.fstat(current)
            if (check.st_dev, check.st_ino) != (parent_identity.st_dev, parent_identity.st_ino):
                raise OSError("bundle directory was replaced")
            for name, identity in observed:
                fd = _open_file(current, name)
                try:
                    if _identity(os.fstat(fd)) != identity:
                        raise OSError("bundle shard was replaced")
                finally:
                    os.close(fd)
        finally:
            os.close(current)
        report = {"schema": "skeleton.gguf.shard-audit.v1",
                  "status": "artifact_bundle_verified_not_loaded",
                  "gguf_version": version, "shard_count": count,
                  "tensor_count": tensors, "total_bytes": used, "shards": rows,
                  "activation_authorized": False}
        report["bundle_sha256"] = hashlib.sha256(json.dumps(
            report, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode()).hexdigest()
        return report
    finally:
        os.close(directory)


def split_identity(pins: Sequence[str]) -> str:
    """Ordered content identity, independent of path and physical file metadata."""
    if (not isinstance(pins, (tuple, list)) or not 2 <= len(pins) <= _MAX_SHARDS
            or any(not isinstance(p, str) or not _HEX.fullmatch(p) for p in pins)
            or len(set(pins)) != len(pins)):
        raise ValueError("split model requires 2–128 distinct ordered SHA-256 pins")
    return hashlib.sha256(b"skeleton.gguf.ordered-shards.v1\0" +
                          b"".join(bytes.fromhex(p) for p in pins)).hexdigest()


def bundle_paths(first: Path, pins: Sequence[str]) -> tuple[Path, ...]:
    split_identity(pins)
    match = _NAME.fullmatch(first.name)
    if not match or int(match.group(2)) != len(pins):
        raise ValueError("first shard filename does not match ordered bundle")
    prefix = match.group(1)
    return tuple(first.with_name(f"{prefix}-{i+1:05d}-of-{len(pins):05d}.gguf")
                 for i in range(len(pins)))


def admit_native_bundle(first: Path, pins: Sequence[str], *,
                        max_bytes: int = _MAX_BYTES,
                        interrupt: Callable[[], None] | None = None) -> dict:
    split_identity(pins)
    return audit_bundle(first, pins, max_bytes=max_bytes, private=True, interrupt=interrupt)
