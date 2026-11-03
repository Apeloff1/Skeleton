"""Descriptor-anchored, bounded, fail-closed import of untrusted game assets.

Never resolve an untrusted package path and subsequently reopen it by name:
all path components are opened relative to a held directory descriptor, with
O_NOFOLLOW on directories, leaves and external references.
"""
from __future__ import annotations

import errno
import os
import stat
import unicodedata
from itertools import islice
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Iterable

from .importers import _EXT, MAX_ASSET_BYTES, AssetImportError, import_bytes
from .manifest import AssetManifest

MAX_IMPORT_FILES = 8192
MAX_TREE_ENTRIES = 16384
MAX_TREE_DEPTH = 32
MAX_IMPORT_TOTAL_BYTES = 512 * 1024 * 1024
MAX_EXTERNAL_REFS_PER_ASSET = 256
MAX_TOTAL_EXTERNAL_REFS = 8192
MAX_EXTERNAL_TOTAL_BYTES = 512 * 1024 * 1024

# A platform without dir_fd + O_NOFOLLOW must not silently downgrade to a
# check-then-open path traversal. A native Windows handle backend is separate.
_DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
# O_NONBLOCK prevents a hostile FIFO leaf from hanging open() before fstat.
# O_NOCTTY prevents a swapped terminal device from becoming the controller.
_FILE_FLAGS = (
    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOCTTY", 0)
)
_SECURE_OPEN = (
    hasattr(os, "O_DIRECTORY")
    and hasattr(os, "O_NOFOLLOW")
    and hasattr(os, "O_NONBLOCK")
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
    if any(unicodedata.category(char) in {"Cc", "Cf", "Zl", "Zp"} for char in relative):
        raise AssetImportError("unsafe asset path control character")
    parts = tuple(relative.split("/"))
    if len(parts) > MAX_TREE_DEPTH or any(part in ("", ".", "..") for part in parts):
        raise AssetImportError("unsafe asset path")
    return parts


def _root_fd(root: str | Path) -> int:
    """Open every root ancestor relative to a held directory descriptor.

    O_NOFOLLOW protects only the final component of an os.open(path) call.
    Opening a whole root pathname would silently follow a symlink in one of
    its parents, even though subsequent asset opens use dir_fd correctly.
    """
    if not _SECURE_OPEN:
        raise AssetImportError("descriptor-anchored asset import is unavailable on this platform")
    source = os.fspath(root)
    if (not isinstance(source, str) or not source or len(source) > 4096
            or "\x00" in source or source.startswith("//")):
        raise AssetImportError("unsafe import root")
    components = [part for part in source.split("/") if part and part != "."]
    if ".." in components or len(components) > 128:
        raise AssetImportError("unsafe import root")
    current = os.open("/" if source.startswith("/") else ".", _DIR_FLAGS)
    try:
        for component in components:
            child = os.open(component, _DIR_FLAGS, dir_fd=current)
            os.close(current)
            current = child
        return current
    except BaseException:
        os.close(current)
        raise


def _regular(
    root_fd: int, relative: str, *, read: bool,
    observed: dict[str, tuple[int, ...]] | None = None,
) -> bytes | int:
    parts = _parts(relative)
    parent = os.dup(root_fd)
    try:
        for index, component in enumerate(parts[:-1]):
            child = os.open(component, _DIR_FLAGS, dir_fd=parent)
            try:
                if observed is not None:
                    prefix = "/".join(parts[:index + 1])
                    snapshot = observed.get(prefix)
                    opened = os.fstat(child)
                    if snapshot != (opened.st_dev, opened.st_ino):
                        raise AssetImportError("directory changed after scan")
            except BaseException:
                os.close(child)
                raise
            os.close(parent)
            parent = child
        leaf = os.open(parts[-1], _FILE_FLAGS, dir_fd=parent)
        try:
            before = os.fstat(leaf)
            if not stat.S_ISREG(before.st_mode):
                raise AssetImportError("asset is not a regular file")
            # A hard link can alias bytes outside the held package tree.
            # Descriptor anchoring alone cannot prove hard-link provenance.
            if before.st_nlink != 1:
                raise AssetImportError("hard-linked asset source is unsafe")
            if before.st_size > MAX_ASSET_BYTES:
                raise AssetImportError("asset exceeds size limit")
            if observed is not None:
                snapshot = observed.get(relative)
                opened = (before.st_dev, before.st_ino, before.st_size,
                          before.st_mtime_ns, before.st_ctime_ns)
                if snapshot != opened:
                    raise AssetImportError("asset changed after directory scan")
            if not read:
                return before.st_size
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
            # mtime may be restored by a concurrent writer. ctime is owned
            # by the filesystem and also detects same-size in-place rewrites.
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns
            ) or count != before.st_size:
                raise AssetImportError("asset changed during descriptor read")
            return b"".join(chunks)
        finally:
            os.close(leaf)
    finally:
        os.close(parent)


def _issue_code(error: OSError) -> str:
    return "missing" if error.errno == errno.ENOENT else "unsafe"


def _check_references(
    root_fd: int, report: ImportReport,
    observed: dict[str, tuple[int, ...]] | None = None,
) -> bool:
    total_refs = 0
    total_bytes = 0
    charged_paths: set[str] = set()
    for entry in report.manifest.entries:
        refs = entry.metadata.get("external_refs", [])
        if type(refs) not in (list, tuple) or len(refs) > MAX_EXTERNAL_REFS_PER_ASSET:
            report.issues.append(ImportIssue(entry.path, "broken",
                                             "external reference count exceeds bound"))
            return False
        # Deduplication collapses identical bytes, not their source-relative
        # dependencies. Every alias must resolve its own sidecars; checking
        # only the canonical path silently trusts missing or swapped inputs.
        for source_path in (entry.path, *entry.aliases):
            if total_refs + len(refs) > MAX_TOTAL_EXTERNAL_REFS:
                report.issues.append(ImportIssue(source_path, "broken",
                                                 "external reference count exceeds bound"))
                return False
            total_refs += len(refs)
            for ref in refs:
                try:
                    _parts(ref)
                    relative = (PurePosixPath(source_path).parent / ref).as_posix()
                    _parts(relative)
                    sidecar_size = _regular(root_fd, relative, read=False, observed=observed)
                    if not isinstance(sidecar_size, int):
                        raise AssetImportError("external reference size unavailable")
                    if relative not in charged_paths:
                        total_bytes += sidecar_size
                        if total_bytes > MAX_EXTERNAL_TOTAL_BYTES:
                            report.issues.append(ImportIssue(source_path, "broken",
                                                             "aggregate external reference bytes exceed bound"))
                            return False
                        charged_paths.add(relative)
                except (AssetImportError, OSError, ValueError, TypeError) as exc:
                    report.issues.append(ImportIssue(source_path, "missing_reference", f"{ref}: {exc}"))
    return True


def _import_from_fd(
    root_fd: int, paths: Iterable[str],
    observed: dict[str, tuple[int, ...]] | None = None,
) -> ImportReport:
    """Import and validate against the exact held root descriptor."""
    report = ImportReport(AssetManifest())
    # Consume only a bounded prefix, then sort for deterministic manifests.
    # Do not materialize an attacker-controlled unbounded path iterator.
    try:
        requested = list(islice(iter(paths), MAX_IMPORT_FILES + 1))
    except Exception:
        # An untrusted producer may fail after yielding otherwise valid paths.
        # Never publish a partial batch or leak arbitrary iterator exceptions.
        report.issues.append(ImportIssue(".", "unsafe", "asset path iterator failed"))
        return report
    if len(requested) > MAX_IMPORT_FILES:
        report.issues.append(ImportIssue(".", "broken", "file count exceeds bound"))
        # A global input bound is a transaction boundary: never publish a
        # plausible partial manifest from an oversized untrusted package.
        return report
    validated: set[str] = set()
    for item in requested:
        if type(item) is not str:
            # Do not invoke __str__, __hash__ or comparison hooks on hostile
            # string subclasses or non-text objects during validation.
            report.issues.append(ImportIssue("<non-text>", "unsafe", "non-text path"))
        else:
            validated.add(item)
    total = 0
    for relative in sorted(validated):
        try:
            parts = _parts(relative)
            if PurePosixPath(parts[-1]).suffix.lower() not in _EXT:
                report.issues.append(ImportIssue(relative, "unsupported", "unsupported extension"))
                continue
            payload = _regular(root_fd, relative, read=True, observed=observed)
            assert isinstance(payload, bytes)
            total += len(payload)
            if total > MAX_IMPORT_TOTAL_BYTES:
                report.issues.append(ImportIssue(relative, "broken", "aggregate asset bytes exceed bound"))
                # Discard prior assets, not just the oversized leaf: callers
                # must never observe a partial manifest after a global cap.
                return ImportReport(AssetManifest(), issues=report.issues)
            asset = import_bytes(relative, payload)
            added = report.manifest.add(asset)
            (report.imported if added else report.duplicates).append(relative)
        except AssetImportError as exc:
            code = "unsafe" if ("unsafe asset path" in str(exc) or "unavailable" in str(exc)
                                or "hard-linked" in str(exc)) else "broken"
            report.issues.append(ImportIssue(relative, code, str(exc)))
        except OSError as exc:
            report.issues.append(ImportIssue(relative, _issue_code(exc), str(exc)))
    if not _check_references(root_fd, report, observed=observed):
        return ImportReport(AssetManifest(), issues=report.issues)
    # A rejected input, including an unresolved sidecar, invalidates the
    # entire explicit file batch. Consumers must never be able to publish a
    # valid-looking partial manifest by overlooking report.ok.
    if report.issues:
        return ImportReport(AssetManifest(), issues=report.issues)
    return report


def import_files(root: str | Path, paths: Iterable[str]) -> ImportReport:
    """Import bounded files without reopening an untrusted path after validation."""
    try:
        root_fd = _root_fd(root)
    except (OSError, AssetImportError) as exc:
        return ImportReport(AssetManifest(), issues=[ImportIssue(".", "unsafe", str(exc))])
    try:
        return _import_from_fd(root_fd, paths)
    finally:
        os.close(root_fd)


def import_directory(root: str | Path) -> ImportReport:
    """Scan a bounded descriptor-held tree; never follow symlink directories."""
    issues: list[ImportIssue] = []
    paths: list[str] = []
    # Bounded identities for every scanned directory and regular file.
    # These bind later descriptor opens to the enumerated tree snapshot.
    observed: dict[str, tuple[int, ...]] = {}
    try:
        root_fd = _root_fd(root)
    except (OSError, AssetImportError) as exc:
        return ImportReport(AssetManifest(), issues=[ImportIssue(".", "unsafe", str(exc))])
    visited = 0

    def walk(directory_fd: int, prefix: str, depth: int) -> None:
        nonlocal visited
        if visited > MAX_TREE_ENTRIES or len(paths) > MAX_IMPORT_FILES:
            return
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
                        snapshot = entry.stat(follow_symlinks=False)
                        if stat.S_ISLNK(snapshot.st_mode):
                            continue
                        if stat.S_ISDIR(snapshot.st_mode):
                            child = os.open(entry.name, _DIR_FLAGS, dir_fd=directory_fd)
                            try:
                                opened = os.fstat(child)
                                if (snapshot.st_dev, snapshot.st_ino) != (opened.st_dev, opened.st_ino):
                                    raise AssetImportError("directory changed during traversal")
                                observed[relative] = (opened.st_dev, opened.st_ino)
                                walk(child, relative + "/", depth + 1)
                            finally:
                                os.close(child)
                        elif stat.S_ISREG(snapshot.st_mode):
                            observed[relative] = (
                                snapshot.st_dev, snapshot.st_ino, snapshot.st_size,
                                snapshot.st_mtime_ns, snapshot.st_ctime_ns,
                            )
                            if PurePosixPath(relative).suffix.lower() in _EXT:
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
        if any(
            issue.detail in {
                "tree entries exceed bound",
                "file count exceeds bound",
                "directory depth exceeds bound",
            }
            for issue in issues
        ):
            return ImportReport(AssetManifest(), issues=issues)
        report = _import_from_fd(root_fd, sorted(paths[:MAX_IMPORT_FILES]), observed=observed)
    finally:
        os.close(root_fd)
    report.issues.extend(issues)
    # A hostile tree scan, changed scanned inode, or missing/rewritten sidecar
    # invalidates the entire directory snapshot. Never expose earlier assets
    # from that snapshot as a plausible partial import transaction.
    if issues or any(
        issue.code in {"unsafe", "missing_reference"} or "changed" in issue.detail
        for issue in report.issues
    ):
        return ImportReport(AssetManifest(), issues=report.issues)
    return report
