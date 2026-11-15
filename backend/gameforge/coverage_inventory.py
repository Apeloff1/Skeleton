"""Bounded, non-executable GameForge source inventory.

A source declaration proves discovery, not importability, runtime behavior,
archive correspondence or production readiness. Never import source selected
by this module. The operator must separately qualify native/device execution.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import stat
import threading
import time
from dataclasses import dataclass
from pathlib import Path

_SUFFIXES = ("Engine", "System", "Orchestrator", "Forge")
_MAX_FILE_BYTES = 2 * 1024 * 1024
_MAX_TOTAL_BYTES = 128 * 1024 * 1024
_MAX_FILES = 10000
_MAX_ENTRIES = 40000
_MAX_SECONDS = 12.0
_CACHE_SECONDS = 60.0


@dataclass(frozen=True)
class SourceRecord:
    path: str
    sha256: str | None
    size: int
    classes: tuple[str, ...]
    status: str

    def as_dict(self) -> dict:
        return {"path": self.path, "sha256": self.sha256, "size_bytes": self.size,
                "classes": list(self.classes), "status": self.status}


@dataclass(frozen=True)
class Inventory:
    records: tuple[SourceRecord, ...]
    complete: bool
    stop_reason: str | None
    bytes_read: int
    directory_errors: int
    created_at: float
    manifest_sha256: str

    @property
    def engine_records(self) -> tuple[SourceRecord, ...]:
        return tuple(row for row in self.records if row.status == "parsed" and row.classes)

    @property
    def errors(self) -> int:
        return self.directory_errors + sum(row.status != "parsed" for row in self.records)

    def summary(self) -> dict:
        engines = self.engine_records
        return {
            "scope": "static_python_source_declarations",
            "complete": self.complete,
            "stop_reason": self.stop_reason,
            "source_files": len(self.records),
            "parsed_files": sum(row.status == "parsed" for row in self.records),
            "source_errors": self.errors,
            "bytes_read": self.bytes_read,
            "manifest_sha256": self.manifest_sha256,
            "total_engine_modules": len(engines),
            "engine_classes": sum(len(row.classes) for row in engines),
            "discovered": len(engines),
            "live": 0,
            "runtime_verified": 0,
            "failed": self.errors,
            "dormant_now": None,
            "unqualified": len(engines),
            "activation_allowed": False,
            "runtime_qualified": False,
            "discovered_detail": [row.path[:-3].replace("/", ".") for row in engines[:100]],
            "failed_detail": [row.path for row in self.records if row.status != "parsed"][:100],
            "ts": self.created_at,
        }

    def page(self, offset: int, limit: int, status: str = "engines") -> dict:
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("invalid inventory page")
        if status == "engines":
            rows = self.engine_records
        elif status == "errors":
            rows = tuple(row for row in self.records if row.status != "parsed")
        elif status == "all":
            rows = self.records
        else:
            raise ValueError("invalid inventory filter")
        end = min(len(rows), offset + limit)
        return {"offset": offset, "limit": limit, "total": len(rows),
                "next_offset": end if end < len(rows) else None,
                "records": [row.as_dict() for row in rows[offset:end]],
                "manifest_sha256": self.manifest_sha256, "complete": self.complete}


def _identity(info: os.stat_result) -> tuple:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _read_source(path: Path, byte_limit: int) -> bytes:
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("nonregular_source")
    if before.st_size > byte_limit:
        raise ValueError("source_size_limit")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or _identity(opened) != _identity(before):
            raise ValueError("source_changed")
        data = stream.read(byte_limit + 1)
        if (len(data) > byte_limit or len(data) != before.st_size
                or _identity(os.fstat(stream.fileno())) != _identity(before)
                or _identity(path.lstat()) != _identity(before)):
            raise ValueError("source_changed")
        return data


def scan_sources(root: Path) -> Inventory:
    started = time.monotonic()
    root = Path(root)
    records: list[SourceRecord] = []
    directory_errors = 0
    total_bytes = 0
    total_entries = 0
    stop = None

    def walk_error(_: OSError):
        nonlocal directory_errors
        directory_errors += 1

    if root.is_symlink() or not root.is_dir():
        stop = "source_root_unavailable"
    else:
        for directory, dirs, files in os.walk(root, topdown=True, followlinks=False, onerror=walk_error):
            total_entries += len(dirs) + len(files)
            if total_entries > _MAX_ENTRIES or time.monotonic() - started > _MAX_SECONDS:
                stop = "scan_budget_reached"
                break
            folder = Path(directory)
            # Symlinked directories are not part of the trusted static inventory.
            retained_dirs = []
            for name in sorted(dirs):
                if name in {"__pycache__", ".git", ".pytest_cache"}:
                    continue
                if (folder / name).is_symlink():
                    directory_errors += 1
                else:
                    retained_dirs.append(name)
            dirs[:] = retained_dirs
            for filename in sorted(files):
                if not filename.endswith(".py") or filename.startswith("__"):
                    continue
                if (len(records) >= _MAX_FILES or total_bytes >= _MAX_TOTAL_BYTES
                        or time.monotonic() - started > _MAX_SECONDS):
                    stop = "scan_budget_reached"
                    break
                path = folder / filename
                relative = "gameforge/" + path.relative_to(root).as_posix()
                data = None
                digest = None
                classes: tuple[str, ...] = ()
                status = "parsed"
                try:
                    remaining = _MAX_TOTAL_BYTES - total_bytes
                    data = _read_source(path, min(remaining, _MAX_FILE_BYTES))
                    total_bytes += len(data)
                    digest = hashlib.sha256(data).hexdigest()
                    syntax = ast.parse(data, filename=relative)
                    classes = tuple(sorted({node.name for node in syntax.body
                                           if isinstance(node, ast.ClassDef)
                                           and node.name.endswith(_SUFFIXES)}))
                except SyntaxError:
                    status = "syntax_error"
                except (UnicodeError, RecursionError, MemoryError):
                    status = "parse_unavailable"
                except ValueError as exc:
                    status = str(exc) if str(exc) in {"nonregular_source", "source_size_limit", "source_changed"} else "parse_unavailable"
                except OSError:
                    status = "read_unavailable"
                records.append(SourceRecord(relative, digest, len(data) if data is not None else 0, classes, status))
            if stop:
                break
    records.sort(key=lambda row: row.path)
    complete = stop is None and directory_errors == 0 and all(row.status == "parsed" for row in records)
    # Domain-separated deterministic digest commits to source paths, bytes,
    # declared classes, outcomes and completeness, not wall-clock timestamps.
    serialized = json.dumps({"format": "gameforge-source-inventory-v1",
        "complete": complete, "stop_reason": stop, "directory_errors": directory_errors,
        "records": [row.as_dict() for row in records]},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return Inventory(tuple(records), complete, stop, total_bytes, directory_errors,
                     time.time(), hashlib.sha256(serialized).hexdigest())


class InventoryCache:
    def __init__(self, root: Path):
        self._root = Path(root)
        self._lock = threading.Lock()
        self._snapshot: Inventory | None = None
        self._expires = 0.0

    def get(self) -> Inventory:
        with self._lock:
            now = time.monotonic()
            if self._snapshot is None or now >= self._expires:
                self._snapshot = scan_sources(self._root)
                self._expires = time.monotonic() + _CACHE_SECONDS
            return self._snapshot
