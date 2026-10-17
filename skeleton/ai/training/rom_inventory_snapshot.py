"""Frozen, source-pinned ROM inventory for large, resumable operator training.

One full bounded root scan becomes an append-only manifest. Only the selected
page is rehashed when consumed, so later pages cannot silently assume files
still exist unchanged. No ROM bytes leave the machine or enter the manifest.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping

from .rom_study import (
    INVENTORY_SCHEMA, MAX_DIRS, MAX_FILES, MAX_PAGE, RomStudyError,
    _AMBIGUOUS, _DISC_DESCRIPTORS, _canonical, _hash,
    _private_output, _recognized_extensions, _regular_identity,
    _safe_path, _save_new, _stream_identity,
)

SCHEMA = "skeleton.jeeves.frozen_rom_inventory.v1"
MAX_SNAPSHOT_BYTES = 32 * 1024 * 1024
_SAFE_FILE = re.compile(r"[A-Za-z0-9_.-]{3,80}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")


def _relative(value: Any) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 4096:
        raise RomStudyError("frozen ROM identity path must be bounded")
    parsed = PurePosixPath(value)
    if (parsed.is_absolute() or str(parsed) != value
            or any(part in ("", ".", "..") for part in parsed.parts)
            or "\x00" in value or "\\" in value):
        raise RomStudyError("frozen ROM identity path is unsafe")
    return value


def freeze_rom_inventory(root: Path, destination: Path, *,
                         name: str = "rom-library-snapshot.json") -> dict[str, Any]:
    """Create an immutable local inventory, never expose ROM contents."""
    root = _safe_path(root, directory=True)
    destination = _private_output(destination)
    if not isinstance(name, str) or not _SAFE_FILE.fullmatch(name) or not name.endswith(".json"):
        raise RomStudyError("frozen inventory name must be a safe JSON basename")
    if destination.is_relative_to(root) or root.is_relative_to(destination):
        raise RomStudyError("private inventory cannot be nested inside ROM content root")
    path = destination / name
    if path.exists() or path.is_symlink():
        raise RomStudyError("frozen inventory destination already exists")
    extensions = _recognized_extensions()
    rows, directory_count = [], 0

    def on_error(exc: OSError):
        raise RomStudyError("frozen ROM inventory directory is unreadable") from exc

    for base, folders, files in os.walk(root, topdown=True, followlinks=False, onerror=on_error):
        directory_count += 1
        if directory_count > MAX_DIRS:
            raise RomStudyError("frozen ROM inventory exceeds directory budget")
        base_path = _safe_path(Path(base), directory=True)
        folders[:] = sorted(name for name in folders if not (base_path / name).is_symlink())
        for filename in sorted(files):
            file = base_path / filename
            if file.is_symlink() or file.suffix.lower() not in extensions:
                continue
            if len(rows) >= MAX_FILES:
                raise RomStudyError("frozen ROM inventory exceeds file capacity")
            relative = _relative(file.relative_to(root).as_posix())
            digest, size, _ = _stream_identity(file)
            rows.append({
                "relative_path": relative, "file_sha256": digest,
                "size_bytes": size, "extension": file.suffix.lower(),
            })
    rows.sort(key=lambda row: row["relative_path"])
    body = {
        "schema_version": SCHEMA,
        "root": str(root),
        "file_count": len(rows),
        "entries": rows,
    }
    body["inventory_sha256"] = _hash(_canonical(body))
    written_sha = _save_new(path, body)
    return {
        "schema_version": SCHEMA,
        "manifest_path": str(path),
        "manifest_sha256": written_sha,
        "inventory_sha256": body["inventory_sha256"],
        "file_count": len(rows),
        "source_bytes_exported": False,
        "training_executed": False,
    }


def load_frozen_inventory(path: Path, *, root: Path) -> dict[str, Any]:
    """Validate one frozen census before page iteration, without re-scanning root."""
    path = _safe_path(path)
    actual_root = _safe_path(root, directory=True)
    fingerprint = _regular_identity(path)
    if fingerprint[2] > MAX_SNAPSHOT_BYTES:
        raise RomStudyError("frozen ROM inventory exceeds maximum bytes")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        from .rom_study import _stat_tuple
        if _stat_tuple(os.fstat(fd)) != fingerprint:
            raise RomStudyError("frozen ROM inventory changed before read")
        with os.fdopen(os.dup(fd), "rb") as stream:
            raw = stream.read(MAX_SNAPSHOT_BYTES + 1)
        if len(raw) != fingerprint[2] or _stat_tuple(os.fstat(fd)) != fingerprint:
            raise RomStudyError("frozen ROM inventory changed during read")
    finally:
        os.close(fd)
    if _regular_identity(path) != fingerprint:
        raise RomStudyError("frozen ROM inventory changed after reading")

    def unique(items):
        record = {}
        for key, value in items:
            if key in record:
                raise RomStudyError("frozen ROM inventory contains duplicate fields")
            record[key] = value
        return record
    try:
        result = json.loads(raw, object_pairs_hook=unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(
                                RomStudyError("nonfinite frozen inventory value")))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise RomStudyError("malformed frozen ROM inventory") from exc
    if (not isinstance(result, dict) or set(result) != {
        "schema_version", "root", "file_count", "entries", "inventory_sha256"
    } or result["schema_version"] != SCHEMA or result["root"] != str(actual_root)):
        raise RomStudyError("frozen ROM inventory root or schema does not match")
    digest = result.pop("inventory_sha256")
    if not isinstance(digest, str) or not _SHA.fullmatch(digest) or _hash(_canonical(result)) != digest:
        raise RomStudyError("frozen ROM inventory checksum differs")
    result["inventory_sha256"] = digest
    rows = result["entries"]
    if (not isinstance(rows, list) or len(rows) > MAX_FILES
            or type(result["file_count"]) is not int or result["file_count"] != len(rows)):
        raise RomStudyError("frozen ROM inventory contains an invalid number of entries")
    supported = _recognized_extensions()
    previous = None
    for item in rows:
        if not isinstance(item, dict) or set(item) != {
            "relative_path", "file_sha256", "size_bytes", "extension"
        }:
            raise RomStudyError("frozen ROM entry schema differs")
        name = _relative(item["relative_path"])
        if previous is not None and name <= previous:
            raise RomStudyError("frozen ROM paths must be distinct and sorted")
        previous = name
        if (not isinstance(item["file_sha256"], str) or not _SHA.fullmatch(item["file_sha256"])
                or type(item["size_bytes"]) is not int
                or not 1 <= item["size_bytes"] <= 2 * 1024**3
                or item["extension"] != PurePosixPath(name).suffix.lower()
                or item["extension"] not in supported):
            raise RomStudyError("frozen ROM content identity or format is invalid")
    return result


def frozen_inventory_page(snapshot: Mapping[str, Any], *, root: Path,
                          cursor: str | None = None,
                          limit: int = 64) -> dict[str, Any]:
    """Page verified snapshot entries; recheck the exact source before execution."""
    if (type(limit) is not int or not 1 <= limit <= MAX_PAGE
            or snapshot.get("schema_version") != SCHEMA):
        raise RomStudyError("frozen ROM page configuration invalid")
    actual_root = _safe_path(root, directory=True)
    if snapshot.get("root") != str(actual_root):
        raise RomStudyError("frozen ROM root changed")
    if cursor is not None:
        _relative(cursor)
    entries = snapshot["entries"]
    # Entries were checked for strictly sorted unique names at manifest load.
    # A whole-library name projection for *every* page makes a year-long
    # 100,000-ROM sweep quadratic in inventory size. Instead, binary-search
    # the existing immutable entry list in logarithmic comparisons.
    start = 0
    if cursor is not None:
        left, right = 0, len(entries)
        while left < right:
            middle = (left + right) // 2
            if entries[middle]["relative_path"] <= cursor:
                left = middle + 1
            else:
                right = middle
        start = left
    page = entries[start:start + limit]
    results = []
    for entry in page:
        path = actual_root / entry["relative_path"]
        try:
            sha, size, _ = _stream_identity(path, expected=entry["file_sha256"])
            if size != entry["size_bytes"]:
                raise RomStudyError("frozen ROM size changed")
            ext = entry["extension"]
            state = ("requires_companion_bundle" if ext in _DISC_DESCRIPTORS
                     else "requires_explicit_platform" if ext in _AMBIGUOUS
                     else "requires_operator_approval")
            results.append({
                **entry, "file_sha256": sha, "size_bytes": size,
                "state": state, "authorized_for_training": False,
                "emulator_execution_checked": False,
            })
        except (RomStudyError, OSError) as exc:
            results.append({
                "relative_path": entry["relative_path"],
                "state": "identity_unavailable", "failure_type": type(exc).__name__,
                "authorized_for_training": False, "emulator_execution_checked": False,
            })
    next_cursor = page[-1]["relative_path"] if start + len(page) < len(entries) and page else None
    return {
        "schema_version": INVENTORY_SCHEMA,
        "root": str(actual_root), "total_candidate_files": len(entries),
        "candidate_extensions": len(_recognized_extensions()),
        "cursor": cursor, "next_cursor": next_cursor, "rows": results,
        "finished": next_cursor is None, "frozen_inventory_sha256": snapshot["inventory_sha256"],
        "rom_bytes_exported": False, "training_executed": False,
    }
