"""No-follow, budgeted read-only adapter for compressed knowledge collections.

This adapter is used by both HTTP routes and the tool runtime. Caller-controlled
collection names must remain logical identifiers; no caller can choose an on-disk
path, traverse symlinks, decompress unbounded data or cause arbitrary file reads.
"""
from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path
from typing import Iterator, Optional

from core.vault_secure_fs import VaultPathError, anchored_directory, read_regular

try:
    import zstandard as zstd
    _HAS_ZSTD = True
except ImportError:
    zstd = None
    _HAS_ZSTD = False

VAULT_DIR = Path("/app/backend/data/vault/compressed")
_MAX_COMPRESSED_BYTES = 128 * 1024 * 1024
_MAX_EXPANDED_SCAN_BYTES = 64 * 1024 * 1024
_MAX_LINE_BYTES = 1024 * 1024
_MAX_RESULTS = 100
_MAX_COLLECTIONS = 20_000
_VALID_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z", re.ASCII)


def _validate_collection(value: str) -> str:
    if (
        not isinstance(value, str)
        or not _VALID_NAME.fullmatch(value)
        or value.endswith(".")
        or value in {".", ".."}
    ):
        raise ValueError("invalid vault collection identifier")
    return value


def _valid_limit(value: int) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_RESULTS:
        raise ValueError("vault sample size must be within allowed bounds")
    return value


def _safe_vault_names(directory: int) -> list[str]:
    """List only bounded single-link regular compressed shards under the pinned fd."""
    names = []
    inspected = 0
    for name in os.listdir(directory):
        inspected += 1
        if inspected > _MAX_COLLECTIONS:
            raise ValueError("vault collection inventory exceeds limit")
        if not name.endswith(".jsonl.zst"):
            continue
        try:
            _validate_collection(name[:-len(".jsonl.zst")])
            info = os.stat(name, dir_fd=directory, follow_symlinks=False)
        except (ValueError, FileNotFoundError):
            continue
        if (
            stat.S_ISREG(info.st_mode)
            and info.st_nlink == 1
            and 0 <= info.st_size <= _MAX_COMPRESSED_BYTES
        ):
            names.append(name)
    return names


def list_collections() -> list[str]:
    try:
        with anchored_directory(VAULT_DIR) as directory:
            return sorted(name[:-len(".jsonl.zst")] for name in _safe_vault_names(directory))
    except FileNotFoundError:
        return []


def _decode_row(raw: bytes) -> dict:
    if len(raw) > _MAX_LINE_BYTES:
        raise ValueError("vault row exceeds decompressed byte limit")

    def _unique_pairs(pairs):
        value = {}
        for k, v in pairs:
            if k in value:
                raise ValueError("duplicate JSON field in vault row")
            value[k] = v
        return value

    def _reject_constant(_):
        raise ValueError("vault row contains a nonfinite number")

    row = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_unique_pairs,
        parse_constant=_reject_constant,
    )
    if not isinstance(row, dict):
        raise ValueError("vault row must be an object")
    return row


def _iter_jsonl(path: Path, limit: int = 50) -> Iterator[dict]:
    """Yield at most limit rows using pinned descriptor + bounded streaming.

    Never use Path.exists(), Path.open() or a post-check pathname read. File
    identity is verified by read_regular, and total decompression is bounded
    independently of the number of rows requested.
    """
    limit = _valid_limit(limit)
    if not _HAS_ZSTD or limit == 0:
        return
    if not isinstance(path, Path) or path.parent != VAULT_DIR:
        raise ValueError("vault filename is outside the configured directory")
    name = path.name
    if not name.endswith(".jsonl.zst"):
        raise ValueError("vault file extension is invalid")
    _validate_collection(name[:-len(".jsonl.zst")])
    with anchored_directory(VAULT_DIR) as directory:
        with read_regular(directory, name, max_bytes=_MAX_COMPRESSED_BYTES) as source:
            decompressor = zstd.ZstdDecompressor()
            with decompressor.stream_reader(source) as reader:
                pending = b""
                expanded = 0
                produced = 0
                while produced < limit:
                    chunk = reader.read(64 * 1024)
                    if not chunk:
                        if pending.strip():
                            yield _decode_row(pending)
                        break
                    expanded += len(chunk)
                    if expanded > _MAX_EXPANDED_SCAN_BYTES:
                        raise ValueError("vault decompression exceeds byte limit")
                    pending += chunk
                    while b"\n" in pending and produced < limit:
                        line, pending = pending.split(b"\n", 1)
                        if not line.strip():
                            continue
                        row = _decode_row(line)
                        produced += 1
                        yield row
                    if len(pending) > _MAX_LINE_BYTES:
                        raise ValueError("vault line exceeds decompressed byte limit")


def query_collection(
    collection: str, limit: int = 10, contains: Optional[str] = None,
) -> list[dict]:
    """Read a single validated shard without symlink following or path probes."""
    identifier = _validate_collection(collection)
    limit = _valid_limit(limit)
    if contains is not None and (not isinstance(contains, str) or len(contains) > 512):
        raise ValueError("vault substring filter exceeds limits")
    if limit == 0:
        return []
    needle = contains.casefold() if contains else None
    for filename in (f"{identifier}.jsonl.zst", f"coll__{identifier}.jsonl.zst"):
        output: list[dict] = []
        try:
            for row in _iter_jsonl(VAULT_DIR / filename, limit=min(_MAX_RESULTS, limit * 5) if needle else limit):
                if needle:
                    if needle not in json.dumps(row, ensure_ascii=False).casefold():
                        continue
                output.append(row)
                if len(output) >= limit:
                    break
        except FileNotFoundError:
            continue
        return output
    return []


def query_topic(topic: str, limit: int = 10) -> dict:
    if not isinstance(topic, str) or len(topic) > 512:
        raise ValueError("vault topic exceeds limits")
    limit = _valid_limit(limit)
    norm = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")
    cols = list_collections()
    matches = [c for c in cols if norm and norm in c.lower()]
    if not matches:
        first = norm.split("-")[0]
        if first:
            matches = [c for c in cols if first in c.lower()]
    return {name: query_collection(name, limit=limit) for name in matches[:3]}


def stats() -> dict:
    count = 0
    total_bytes = 0
    names: list[str] = []
    try:
        with anchored_directory(VAULT_DIR) as directory:
            files = _safe_vault_names(directory)
            for name in files:
                info = os.stat(name, dir_fd=directory, follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise VaultPathError("vault shard changed during inventory")
                count += 1
                total_bytes += info.st_size
                if len(names) < 10:
                    names.append(name[:-len(".jsonl.zst")])
    except FileNotFoundError:
        pass
    return {
        "collections": count,
        "total_bytes": total_bytes,
        "has_zstd": _HAS_ZSTD,
        "sample_names": sorted(names),
    }
