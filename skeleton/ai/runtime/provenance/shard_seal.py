"""Offline, fail-closed file-tree Merkle sealing without executing generated code.

A shard must be a single regular file below a pinned directory handle. No
absolute paths, symlinks, nested paths, unbounded file sizes or malformed
manifests are admitted. A seal is an integrity receipt, not a code signature.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence

SEAL_VERSION = 1
MAX_SHARD_BYTES = 64 * 1024 * 1024
MAX_SHARDS = 100_000
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
MAX_SEAL_BYTES = 16 * 1024 * 1024
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_CHUNK = 1024 * 1024

__all__ = ["ShardSealError", "ShardSeal", "merkle_root", "seal_tree", "verify_seal", "shard_names"]


class ShardSealError(RuntimeError):
    """A shard path, file, seal, or publication violates integrity custody."""


def _name(name: object) -> str:
    if type(name) is not str or not _NAME.fullmatch(name) or name in {".", ".."}:
        raise ShardSealError("invalid shard basename")
    return name


def _names(names: Sequence[str]) -> tuple[str, ...]:
    if isinstance(names, (str, bytes)):
        raise ShardSealError("shard names must be a list of basenames")
    if not 1 <= len(names) <= MAX_SHARDS:
        raise ShardSealError("shard count outside admission bound")
    out = tuple(_name(name) for name in names)
    if len(set(out)) != len(out):
        raise ShardSealError("duplicate shard names")
    return out


def merkle_root(leaves: Sequence[bytes]) -> str:
    if not 1 <= len(leaves) <= MAX_SHARDS:
        raise ShardSealError("no leaves or too many leaves")
    level = [hashlib.sha256(b"\x00" + leaf).digest() for leaf in leaves]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [
            hashlib.sha256(b"\x01" + level[i] + level[i + 1]).digest()
            for i in range(0, len(level), 2)
        ]
    return level[0].hex()


def shard_names(count: int, prefix: str = "shard_", suffix: str = ".py") -> List[str]:
    if type(count) is not int or not 1 <= count <= MAX_SHARDS:
        raise ShardSealError("count must be 1..100000")
    if not isinstance(prefix, str) or not isinstance(suffix, str):
        raise ShardSealError("prefix and suffix must be strings")
    width = max(3, len(str(count - 1)))
    return [_name(f"{prefix}{i:0{width}d}{suffix}") for i in range(count)]


def _validate_seal(seal: "ShardSeal") -> tuple[str, ...]:
    if type(seal.version) is not int or seal.version != SEAL_VERSION:
        raise ShardSealError("unsupported seal version")
    if type(seal.expected) is not int or not 1 <= seal.expected <= MAX_SHARDS:
        raise ShardSealError("invalid expected count")
    if type(seal.digests) is not dict or seal.expected != len(seal.digests):
        raise ShardSealError("seal count mismatch")
    names = _names(tuple(seal.digests))
    if not isinstance(seal.root, str) or not _SHA.fullmatch(seal.root):
        raise ShardSealError("invalid Merkle root")
    for name in names:
        value = seal.digests[name]
        if not isinstance(value, str) or not _SHA.fullmatch(value):
            raise ShardSealError("invalid shard digest")
    return names


@dataclass(frozen=True)
class ShardSeal:
    expected: int
    digests: Dict[str, str]
    root: str
    version: int = SEAL_VERSION

    def to_json(self) -> str:
        _validate_seal(self)
        text = json.dumps(
            {"version": self.version, "expected": self.expected,
             "root": self.root, "digests": self.digests},
            indent=2, sort_keys=True,
        )
        if len(text.encode("utf-8")) > MAX_SEAL_BYTES:
            raise ShardSealError("seal exceeds byte cap")
        return text

    @classmethod
    def from_json(cls, text: str) -> "ShardSeal":
        if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_SEAL_BYTES:
            raise ShardSealError("seal is missing or exceeds byte cap")

        def pairs(items):
            out = {}
            for key, value in items:
                if key in out:
                    raise ShardSealError("duplicate seal JSON key")
                out[key] = value
            return out

        try:
            payload = json.loads(text, object_pairs_hook=pairs)
        except (ValueError, TypeError) as exc:
            raise ShardSealError("malformed seal JSON") from exc
        if not isinstance(payload, dict) or set(payload) != {
            "version", "expected", "root", "digests"
        }:
            raise ShardSealError("malformed seal fields")
        seal = cls(payload["expected"], payload["digests"], payload["root"], payload["version"])
        _validate_seal(seal)
        return seal


def _root_fd(root: Path) -> int:
    if root.is_symlink() or not root.is_dir():
        raise ShardSealError("seal root must be a regular directory")
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise ShardSealError("secure directory-relative shard opening is unsupported")
    try:
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            raise ShardSealError("invalid seal root descriptor")
        return fd
    except OSError as exc:
        raise ShardSealError("cannot open seal directory securely") from exc


def _file_digest(root_fd: int, name: str) -> tuple[str, int]:
    fd = None
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root_fd)
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise ShardSealError("shard is not a regular file")
        if st.st_size > MAX_SHARD_BYTES:
            raise ShardSealError("shard too large")
        digest, count = hashlib.sha256(), 0
        while True:
            chunk = os.read(fd, min(_CHUNK, MAX_SHARD_BYTES + 1 - count))
            if not chunk:
                break
            digest.update(chunk)
            count += len(chunk)
            if count > MAX_SHARD_BYTES:
                raise ShardSealError("shard exceeds byte admission bound")
        after = os.fstat(fd)
        if (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ) or count != after.st_size:
            raise ShardSealError("shard changed during sealing")
        return digest.hexdigest(), count
    except FileNotFoundError as exc:
        raise ShardSealError("missing shard") from exc
    except OSError as exc:
        raise ShardSealError("cannot open or read shard securely") from exc
    finally:
        if fd is not None:
            os.close(fd)


def _collect(root: Path, names: Sequence[str]) -> Dict[str, str]:
    wanted = _names(names)
    fd = _root_fd(root)
    try:
        digest_map, total = {}, 0
        for name in wanted:
            digest, size = _file_digest(fd, name)
            digest_map[name] = digest
            total += size
            if total > MAX_TOTAL_BYTES:
                raise ShardSealError("total shard byte budget exceeded")
        return digest_map
    finally:
        os.close(fd)


def _root_of(digests: Dict[str, str]) -> str:
    return merkle_root([f"{n}|{d}".encode("ascii") for n, d in sorted(digests.items())])


def _publication_path(root: Path, dest: Path, names: Sequence[str]) -> Path:
    absolute_root = root.resolve(strict=True)
    # The destination must remain inside the shard root and must not alias a
    # shard. Never write alongside a symlinked output directory.
    absolute_dest = Path(os.path.abspath(dest))
    if ".." in dest.parts or not absolute_dest.is_relative_to(absolute_root):
        raise ShardSealError("seal output must be inside shard root")
    relative = absolute_dest.relative_to(absolute_root)
    if not relative.parts or relative.parts[0] in names:
        raise ShardSealError("seal output aliases a shard")
    current = absolute_root
    for segment in relative.parts[:-1]:
        current = current / segment
        if current.is_symlink():
            raise ShardSealError("seal output directory contains symlink")
    absolute_dest.parent.mkdir(parents=True, exist_ok=True)
    if absolute_dest.parent.resolve(strict=True) != absolute_dest.parent:
        raise ShardSealError("seal output parent changed or is symlinked")
    return absolute_dest


def seal_tree(root: Path, names: Sequence[str], dest: Path | None = None) -> ShardSeal:
    root = Path(root)
    expected = _names(names)
    digests = _collect(root, expected)
    seal = ShardSeal(len(expected), digests, _root_of(digests))
    if dest is not None:
        output = _publication_path(root, Path(dest), expected)
        encoded = seal.to_json().encode("utf-8")
        fd = None
        tmp_name = None
        try:
            fd, tmp_name = tempfile.mkstemp(prefix=".shard-seal-", dir=output.parent)
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as stream:
                fd = None
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp_name, output)
            tmp_name = None
        finally:
            if fd is not None:
                os.close(fd)
            if tmp_name is not None:
                Path(tmp_name).unlink(missing_ok=True)
    return seal


def verify_seal(root: Path, seal: ShardSeal) -> None:
    names = _validate_seal(seal)
    if _root_of(seal.digests) != seal.root:
        raise ShardSealError("seal root does not match its digests")
    current = _collect(Path(root), names)
    changed = [name for name in names if current[name] != seal.digests[name]]
    if changed:
        raise ShardSealError(f"{len(changed)} shard(s) changed")
