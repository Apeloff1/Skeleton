"""Bounded, race-aware, symlink-safe workspace snapshots."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import stat
from typing import Callable, Iterable
import uuid

from skeleton.shells.provenance import canonical_json
from skeleton.shells.workspace_txn.pathing import PathMatcher, normalize_relative_path, root_fingerprint
from skeleton.shells.workspace_txn.types import (
    ScanLimits,
    ScanStatistics,
    SnapshotEntry,
    WorkspaceEntryKind,
    WorkspaceSnapshot,
)


class WorkspaceScanError(RuntimeError):
    pass


@dataclass(frozen=True)
class ScannerConfig:
    limits: ScanLimits = ScanLimits()
    matcher: PathMatcher = PathMatcher()
    fail_on_race: bool = True
    fail_on_error: bool = True


@dataclass
class _Stats:
    files: int = 0
    directories: int = 0
    symlinks: int = 0
    other: int = 0
    hashed_bytes: int = 0
    skipped_bytes: int = 0
    errors: int = 0

    def freeze(self) -> ScanStatistics:
        return ScanStatistics(
            files=self.files,
            directories=self.directories,
            symlinks=self.symlinks,
            other=self.other,
            hashed_bytes=self.hashed_bytes,
            skipped_bytes=self.skipped_bytes,
            errors=self.errors,
        )


def _kind(mode: int) -> WorkspaceEntryKind:
    if stat.S_ISREG(mode):
        return WorkspaceEntryKind.FILE
    if stat.S_ISDIR(mode):
        return WorkspaceEntryKind.DIRECTORY
    if stat.S_ISLNK(mode):
        return WorkspaceEntryKind.SYMLINK
    return WorkspaceEntryKind.OTHER


def _hash_file(path: Path, before: os.stat_result, limits: ScanLimits) -> tuple[str, int]:
    if before.st_size > limits.max_file_bytes:
        raise WorkspaceScanError("file exceeds hash bound")
    digest = hashlib.sha256()
    read_bytes = 0
    try:
        with path.open("rb", buffering=0) as handle:
            opened = os.fstat(handle.fileno())
            if (
                opened.st_dev != before.st_dev
                or opened.st_ino != before.st_ino
                or opened.st_size != before.st_size
                or opened.st_mtime_ns != before.st_mtime_ns
            ):
                raise WorkspaceScanError("file changed before hashing")
            while True:
                chunk = handle.read(limits.hash_chunk_bytes)
                if not chunk:
                    break
                digest.update(chunk)
                read_bytes += len(chunk)
                if read_bytes > limits.max_file_bytes:
                    raise WorkspaceScanError("file grew beyond hash bound")
            after = os.fstat(handle.fileno())
    except OSError as exc:
        raise WorkspaceScanError("failed to hash file") from exc
    if (
        after.st_dev != opened.st_dev
        or after.st_ino != opened.st_ino
        or after.st_size != opened.st_size
        or after.st_mtime_ns != opened.st_mtime_ns
    ):
        raise WorkspaceScanError("file changed while hashing")
    return digest.hexdigest(), read_bytes


def snapshot_digest(entries: Iterable[SnapshotEntry], root_digest: str) -> str:
    payload = {
        "root": root_digest,
        "entries": [entry.to_dict() for entry in entries],
    }
    return hashlib.sha256(canonical_json(payload)).hexdigest()


class WorkspaceScanner:
    def __init__(
        self,
        config: ScannerConfig | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config or ScannerConfig()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _root(root: Path | str) -> Path:
        try:
            value = Path(root).expanduser().resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise WorkspaceScanError("workspace root does not exist") from exc
        if not value.is_dir():
            raise WorkspaceScanError("workspace root must be a directory")
        return value

    def _make_entry(
        self,
        absolute: Path,
        relative: str,
        metadata: os.stat_result,
        stats: _Stats,
    ) -> SnapshotEntry | None:
        limits = self.config.limits
        kind = _kind(metadata.st_mode)
        if kind is WorkspaceEntryKind.FILE:
            digest, count = _hash_file(absolute, metadata, limits)
            stats.files += 1
            stats.hashed_bytes += count
            if stats.hashed_bytes > limits.max_total_hashed_bytes:
                raise WorkspaceScanError("workspace hash budget exceeded")
            return SnapshotEntry(
                relative,
                kind,
                int(metadata.st_size),
                stat.S_IMODE(metadata.st_mode),
                int(metadata.st_mtime_ns),
                digest=digest,
                device=int(metadata.st_dev),
                inode=int(metadata.st_ino),
            )
        if kind is WorkspaceEntryKind.DIRECTORY:
            stats.directories += 1
            if not limits.include_directories:
                return None
            return SnapshotEntry(
                relative,
                kind,
                0,
                stat.S_IMODE(metadata.st_mode),
                int(metadata.st_mtime_ns),
                device=int(metadata.st_dev),
                inode=int(metadata.st_ino),
            )
        if kind is WorkspaceEntryKind.SYMLINK:
            stats.symlinks += 1
            if not limits.include_symlinks:
                return None
            try:
                target = os.readlink(absolute)
            except OSError as exc:
                raise WorkspaceScanError("failed to inspect symlink") from exc
            return SnapshotEntry(
                relative,
                kind,
                int(metadata.st_size),
                stat.S_IMODE(metadata.st_mode),
                int(metadata.st_mtime_ns),
                link_target=os.fsdecode(target),
                device=int(metadata.st_dev),
                inode=int(metadata.st_ino),
            )
        stats.other += 1
        if not limits.include_other:
            return None
        return SnapshotEntry(
            relative,
            kind,
            int(metadata.st_size),
            stat.S_IMODE(metadata.st_mode),
            int(metadata.st_mtime_ns),
            device=int(metadata.st_dev),
            inode=int(metadata.st_ino),
        )

    def scan(self, root: Path | str) -> WorkspaceSnapshot:
        root_path = self._root(root)
        root_digest = root_fingerprint(root_path)
        stats = _Stats()
        entries: list[SnapshotEntry] = []
        excluded: list[str] = []
        stack: list[tuple[Path, str, int]] = [(root_path, "", 0)]
        limits = self.config.limits

        while stack:
            directory, prefix, depth = stack.pop()
            if depth > limits.max_depth:
                raise WorkspaceScanError("workspace scan depth exceeded")
            try:
                children = sorted(os.scandir(directory), key=lambda item: item.name)
            except OSError as exc:
                stats.errors += 1
                if self.config.fail_on_error:
                    raise WorkspaceScanError("failed to enumerate directory") from exc
                continue
            descend: list[tuple[Path, str, int]] = []
            for child in children:
                relative = child.name if not prefix else f"{prefix}/{child.name}"
                normalized = normalize_relative_path(relative)
                if len(normalized.encode("utf-8")) > limits.max_path_bytes:
                    raise WorkspaceScanError("workspace path exceeds byte bound")
                if self.config.matcher.excluded(normalized):
                    excluded.append(normalized)
                    try:
                        metadata = child.stat(follow_symlinks=False)
                        if stat.S_ISREG(metadata.st_mode):
                            stats.skipped_bytes += int(metadata.st_size)
                    except OSError:
                        stats.errors += 1
                    continue
                try:
                    metadata = child.stat(follow_symlinks=False)
                    absolute = Path(child.path)
                    entry = self._make_entry(absolute, normalized, metadata, stats)
                except (OSError, WorkspaceScanError) as exc:
                    stats.errors += 1
                    if self.config.fail_on_error:
                        if isinstance(exc, WorkspaceScanError):
                            raise
                        raise WorkspaceScanError("failed to inspect entry") from exc
                    continue
                if entry is not None and self.config.matcher.matches(normalized):
                    entries.append(entry)
                    if len(entries) > limits.max_entries:
                        raise WorkspaceScanError("workspace entry bound exceeded")
                if (
                    stat.S_ISDIR(metadata.st_mode)
                    and not stat.S_ISLNK(metadata.st_mode)
                    and self.config.matcher.may_descend(normalized)
                ):
                    descend.append((absolute, normalized, depth + 1))
            stack.extend(reversed(descend))

        entries.sort(key=lambda item: item.path)
        return WorkspaceSnapshot(
            root_fingerprint=root_digest,
            created_at=self._clock().isoformat(),
            snapshot_id=uuid.uuid4().hex,
            entries=tuple(entries),
            statistics=stats.freeze(),
            digest=snapshot_digest(entries, root_digest),
            excluded_paths=tuple(sorted(set(excluded))),
        )

    def rescan_paths(self, root: Path | str, paths: Iterable[str]) -> tuple[SnapshotEntry, ...]:
        base = self._root(root)
        stats = _Stats()
        result: list[SnapshotEntry] = []
        for relative in sorted({normalize_relative_path(p) for p in paths}):
            absolute = base.joinpath(*relative.split("/"))
            try:
                metadata = absolute.lstat()
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise WorkspaceScanError("failed to inspect requested path") from exc
            entry = self._make_entry(absolute, relative, metadata, stats)
            if entry is not None:
                result.append(entry)
        return tuple(result)

    def verify(self, root: Path | str, expected: WorkspaceSnapshot) -> bool:
        current = self.scan(root)
        return (
            current.root_fingerprint == expected.root_fingerprint
            and current.digest == expected.digest
        )

    def with_matcher(self, matcher: PathMatcher) -> "WorkspaceScanner":
        return WorkspaceScanner(replace(self.config, matcher=matcher), clock=self._clock)
