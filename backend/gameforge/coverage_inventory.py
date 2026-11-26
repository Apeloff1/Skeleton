"""Bounded static inventory: never import discovered source or invoke routes."""
from __future__ import annotations

import ast
import hashlib
import os
import stat
import time
from dataclasses import dataclass
from pathlib import Path

MAX_FILE_BYTES = 1024 * 1024
MAX_SCAN_BYTES = 128 * 1024 * 1024
MAX_FILES = 30000
MAX_DIRS = 30000
SUFFIXES = ("Engine", "System", "Orchestrator", "Forge")
IGNORED = frozenset({"__pycache__", ".git", ".venv", "node_modules", "data"})


@dataclass(frozen=True)
class ScanLimits:
    files: int = MAX_FILES
    directories: int = MAX_DIRS
    file_bytes: int = MAX_FILE_BYTES
    total_bytes: int = MAX_SCAN_BYTES
    seconds: float = 15.0


def _digest_rows(rows: list[dict]) -> str:
    import json
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=True,
                                     separators=(",", ":")).encode("ascii")).hexdigest()


def scan_source(root: Path, limits: ScanLimits = ScanLimits()) -> dict:
    if (type(limits.files) is not int or not 1 <= limits.files <= MAX_FILES
            or type(limits.directories) is not int or not 1 <= limits.directories <= MAX_DIRS
            or type(limits.file_bytes) is not int or not 1 <= limits.file_bytes <= MAX_FILE_BYTES
            or type(limits.total_bytes) is not int or not 1 <= limits.total_bytes <= MAX_SCAN_BYTES
            or not 0 < limits.seconds <= 30):
        raise ValueError("invalid scan limits")
    started = time.monotonic()
    errors: list[dict] = []
    skipped = 0
    visited = 0
    directories = 0
    bytes_read = 0
    modules: list[dict] = []
    complete = True
    reason = None
    if root.is_symlink() or not root.is_dir():
        raise ValueError("source inventory root is not an ordinary directory")

    def error(relative, code):
        nonlocal skipped
        skipped += 1
        if len(errors) < 200:
            errors.append({"path": relative, "code": code})

    def walk_error(_exc):
        nonlocal complete
        complete = False
        error(".", "directory_unreadable")

    for folder, dirs, files in os.walk(root, topdown=True, followlinks=False, onerror=walk_error):
        directories += 1
        if directories > limits.directories:
            complete, reason = False, "directory_budget"
            break
        if time.monotonic() - started >= limits.seconds:
            complete, reason = False, "time_budget"
            break
        current = Path(folder)
        safe_dirs = []
        for name in sorted(dirs):
            if name in IGNORED:
                continue
            child = current / name
            if child.is_symlink():
                error(child.relative_to(root).as_posix(), "symlink_directory")
            else:
                safe_dirs.append(name)
        dirs[:] = safe_dirs
        for name in sorted(files):
            if not name.endswith(".py") or name.startswith("__"):
                continue
            if visited >= limits.files or time.monotonic() - started >= limits.seconds:
                complete, reason = False, "file_or_time_budget"
                break
            visited += 1
            path = current / name
            relative = path.relative_to(root).as_posix()
            try:
                before = path.lstat()
                if not stat.S_ISREG(before.st_mode):
                    error(relative, "nonregular_source")
                    continue
                if before.st_size > limits.file_bytes:
                    error(relative, "file_byte_budget")
                    continue
                if bytes_read + before.st_size > limits.total_bytes:
                    complete, reason = False, "total_byte_budget"
                    break
                flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
                fd = os.open(path, flags)
                with os.fdopen(fd, "rb") as handle:
                    opened = os.fstat(handle.fileno())
                    if (not stat.S_ISREG(opened.st_mode) or
                            (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)):
                        error(relative, "source_replaced")
                        continue
                    raw = handle.read(min(limits.file_bytes, limits.total_bytes - bytes_read) + 1)
                    after = os.fstat(handle.fileno())
                bytes_read += len(raw)
                if (len(raw) != opened.st_size or after.st_size != opened.st_size or
                        after.st_mtime_ns != opened.st_mtime_ns or len(raw) > limits.file_bytes):
                    error(relative, "unstable_or_oversized_source")
                    continue
                if bytes_read > limits.total_bytes:
                    complete, reason = False, "total_byte_budget"
                    break
                tree = ast.parse(raw, filename=relative)
            except (OSError, SyntaxError, UnicodeError, ValueError, RecursionError, MemoryError):
                error(relative, "source_unreadable_or_invalid")
                continue
            classes = sorted({node.name for node in tree.body
                              if isinstance(node, ast.ClassDef) and node.name.endswith(SUFFIXES)})
            if classes:
                modules.append({"module": "gameforge." + relative[:-3].replace("/", "."),
                                "classes": classes, "source_sha256": hashlib.sha256(raw).hexdigest()})
        if reason:
            break
    modules.sort(key=lambda row: row["module"])
    # A digest commits to the discovered subset; it is never a runtime receipt.
    return {"modules": modules, "inventory_sha256": _digest_rows(modules),
            "files_examined": visited, "bytes_read": bytes_read, "directories_examined": directories,
            "skipped_count": skipped, "errors": errors, "complete": complete and not skipped,
            "stop_reason": reason, "duration_ms": round((time.monotonic() - started) * 1000, 2)}


def route_registration(routes, expected: list[tuple[str, str]]) -> list[dict]:
    """Inspect mounted ASGI route declarations; do not call endpoint functions."""
    paths = sorted({str(route.path) for route in routes
                    if getattr(route, "path", None) and getattr(route, "methods", None)})
    result = []
    for name, prefix in expected:
        matching = [path for path in paths if path == prefix or path.startswith(prefix + "/")]
        result.append({"name": name, "prefix": prefix, "ok": bool(matching),
                       "status": "registered" if matching else "missing",
                       "registered_paths": matching[:12], "route_count": len(matching),
                       "runtime_verified": False, "latency_ms": 0})
    return result
