"""Descriptor-anchored, bounded, fail-closed import of untrusted game assets.

Never resolve an untrusted package path and subsequently reopen it by name:
all path components are opened relative to a held directory descriptor, with
O_NOFOLLOW on directories, leaves and external references.
"""
from __future__ import annotations

import errno
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Iterable

from .importers import _EXT, MAX_ASSET_BYTES, AssetImportError, import_bytes
from .manifest import AssetManifest

MAX_IMPORT_FILES = 8192
MAX_TREE_ENTRIES = 16384
MAX_TREE_DEPTH = 32
MAX_IMPORT_TOTAL_BYTES = 512 * 1024 * 1024

# A platform without dir_fd + O_NOFOLLOW must not silently downgrade to a
# check-then-open path traversal. A native Windows handle backend is separate.
_DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_FILE_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
_SECURE_OPEN = (
    hasattr(os, "O_DIRECTORY")
    and hasattr(os, "O_NOFOLLOW")
    and os.open in os.supports_dir_fd
)


@dataclass(frozen=True)
class ImportIssue:
    path: str
    code: str  # missing | broken | unsupported | unsafe | missing_reference
    detail: str


@dataclass
class ImportReport:
    manifest: AssetManifest
    imported: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    issues: list[ImportIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def _parts(relative: str) -> tuple[str, ...]:
    if not isinstance(relative, str) or not relative or len(relative) > 4096:
        raise AssetImportError("unsafe asset path")
    if any(char in relative for char in ("\\", "\x00", ":", "%", "?", "#")):
        raise AssetImportError("unsafe asset path or URI")
    parts = tuple(relative.split("/"))
    if len(parts) > MAX_TREE_DEPTH or any(part in ("", ".", "..") for part in parts):
        raise AssetImportError("unsafe asset path")
    return parts


def _root_fd(root: str | Path) -> int:
    if not _SECURE_OPEN:
        raise AssetImportError("descriptor-anchored asset import is unavailable on this platform")
    return os.open(os.fspath(root), _DIR_FLAGS)


def _regular(root_fd: int, relative: str, *, read: bool) -> bytes | None:
    parts = _parts(relative)
    parent = os.dup(root_fd)
    try:
        for component in parts[:-1]:
            child = os.open(component, _DIR_FLAGS, dir_fd=parent)
            os.close(parent)
            parent = child
        leaf = os.open(parts[-1], _FILE_FLAGS, dir_fd=parent)
        try:
            before = os.fstat(leaf)
            if not stat.S_ISREG(before.st_mode):
                raise AssetImportError("asset is not a regular file")
            if before.st_size > MAX_ASSET_BYTES:
                raise AssetImportError("asset exceeds size limit")
            if not read:
                return None
            chunks: list[bytes] = []
            count = 0
            while count <= MAX_ASSET_BYTES:
                block = os.read(leaf, min(1024 * 1024, MAX_ASSET_BYTES + 1 - count))
                if not block:
                    break
                count += len(block)
                chunks.append(block)
            after = os.fstat(leaf)
            if count > MAX_ASSET_BYTES:
                raise AssetImportError("asset exceeds size limit")
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
            ) or count != before.st_size:
                raise AssetImportError("asset changed during descriptor read")
            return b"".join(chunks)
        finally:
            os.close(leaf)
    finally:
        os.close(parent)


def _issue_code(error: OSError) -> str:
    return "missing" if error.errno == errno.ENOENT else "unsafe"


def _check_references(root_fd: int, report: ImportReport) -> None:
    for entry in report.manifest.entries:
        for ref in entry.metadata.get("external_refs", []):
            try:
                _parts(ref)
                relative = (PurePosixPath(entry.path).parent / ref).as_posix()
                _regular(root_fd, relative, read=False)
            except (AssetImportError, OSError, ValueError, TypeError) as exc:
                report.issues.append(ImportIssue(entry.path, "missing_reference", f"{ref}: {exc}"))


def import_files(root: str | Path, paths: Iterable[str]) -> ImportReport:
    """Import at most a bounded set of assets, without following symlink edges."""
    report = ImportReport(AssetManifest())
    try:
        root_fd = _root_fd(root)
    except (OSError, AssetImportError) as exc:
        report.issues.append(ImportIssue(".", "unsafe", str(exc)))
        return report
    try:
        # Consume only a bounded prefix, then sort for deterministic manifests.
        # Do not materialize an attacker-controlled unbounded path iterator.
        from itertools import islice

        requested = list(islice(paths, MAX_IMPORT_FILES + 1))
        if len(requested) > MAX_IMPORT_FILES:
            report.issues.append(ImportIssue(".", "broken", "file count exceeds bound"))
            requested = requested[:MAX_IMPORT_FILES]
        total = 0
        for relative in sorted(set(str(item) for item in requested)):
            if not isinstance(relative, str):
                report.issues.append(ImportIssue(str(relative), "unsafe", "non-text path"))
                continue
            try:
                parts = _parts(relative)
                if PurePosixPath(parts[-1]).suffix.lower() not in _EXT:
                    report.issues.append(ImportIssue(relative, "unsupported", "unsupported extension"))
                    continue
                payload = _regular(root_fd, relative, read=True)
                assert payload is not None
                total += len(payload)
                if total > MAX_IMPORT_TOTAL_BYTES:
                    report.issues.append(ImportIssue(relative, "broken", "aggregate asset bytes exceed bound"))
                    break
                asset = import_bytes(relative, payload)
                added = report.manifest.add(asset)
                (report.imported if added else report.duplicates).append(relative)
            except AssetImportError as exc:
                code = "unsafe" if "unsafe asset path" in str(exc) or "unavailable" in str(exc) else "broken"
                report.issues.append(ImportIssue(relative, code, str(exc)))
            except OSError as exc:
                report.issues.append(ImportIssue(relative, _issue_code(exc), str(exc)))
        _check_references(root_fd, report)
    finally:
        os.close(root_fd)
    return report


def import_directory(root: str | Path) -> ImportReport:
    """Scan a bounded descriptor-held tree; never follow symlink directories."""
    issues: list[ImportIssue] = []
    paths: list[str] = []
    try:
        root_fd = _root_fd(root)
    except (OSError, AssetImportError) as exc:
        return ImportReport(AssetManifest(), issues=[ImportIssue(".", "unsafe", str(exc))])
    visited = 0

    def walk(directory_fd: int, prefix: str, depth: int) -> None:
        nonlocal visited
        if depth > MAX_TREE_DEPTH:
            issues.append(ImportIssue(prefix or ".", "unsafe", "directory depth exceeds bound"))
            return
        try:
            with os.scandir(directory_fd) as iterator:
                for entry in iterator:
                    visited += 1
                    if visited > MAX_TREE_ENTRIES:
                        issues.append(ImportIssue(prefix or ".", "broken", "tree entries exceed bound"))
                        return
                    relative = prefix + entry.name
                    try:
                        _parts(relative)
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            child = os.open(entry.name, _DIR_FLAGS, dir_fd=directory_fd)
                            try:
                                walk(child, relative + "/", depth + 1)
                            finally:
                                os.close(child)
                        elif entry.is_file(follow_symlinks=False) and PurePosixPath(relative).suffix.lower() in _EXT:
                            paths.append(relative)
                            if len(paths) > MAX_IMPORT_FILES:
                                issues.append(ImportIssue(relative, "broken", "file count exceeds bound"))
                                return
                    except (OSError, AssetImportError) as exc:
                        issues.append(ImportIssue(relative, "unsafe", str(exc)))
                    if visited > MAX_TREE_ENTRIES or len(paths) > MAX_IMPORT_FILES:
                        return
        except OSError as exc:
            issues.append(ImportIssue(prefix or ".", "unsafe", str(exc)))

    try:
        walk(root_fd, "", 0)
    finally:
        os.close(root_fd)
    report = import_files(root, sorted(paths[:MAX_IMPORT_FILES]))
    report.issues.extend(issues)
    return report
