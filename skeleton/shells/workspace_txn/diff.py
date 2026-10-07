"""Deterministic snapshot differencing with bounded rename detection."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
from typing import Iterable

from skeleton.shells.provenance import canonical_json
from skeleton.shells.workspace_txn.types import (
    ChangeSet,
    ChangeStatistics,
    SnapshotEntry,
    WorkspaceChange,
    WorkspaceChangeKind,
    WorkspaceEntryKind,
    WorkspaceSnapshot,
)


@dataclass(frozen=True)
class DiffConfig:
    detect_renames: bool = True
    require_equal_mode_for_rename: bool = False
    max_rename_candidates_per_digest: int = 64

    def __post_init__(self) -> None:
        value = self.max_rename_candidates_per_digest
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("rename candidate bound must be positive")


def _rename_key(entry: SnapshotEntry, include_mode: bool) -> tuple[object, ...] | None:
    if entry.kind is WorkspaceEntryKind.FILE:
        key: tuple[object, ...] = (entry.kind.value, entry.digest, entry.size)
    elif entry.kind is WorkspaceEntryKind.SYMLINK:
        key = (entry.kind.value, entry.link_target)
    else:
        return None
    return key + ((entry.mode,) if include_mode else ())


def _distance(old: str, new: str) -> tuple[int, int, str]:
    left = old.split("/")
    right = new.split("/")
    common = 0
    for a, b in zip(left, right):
        if a != b:
            break
        common += 1
    return (-common, abs(len(left) - len(right)), new)


def _pair_renames(
    deleted: list[SnapshotEntry],
    created: list[SnapshotEntry],
    config: DiffConfig,
) -> tuple[list[WorkspaceChange], list[SnapshotEntry], list[SnapshotEntry]]:
    if not config.detect_renames:
        return [], deleted, created
    old_groups: dict[tuple[object, ...], list[SnapshotEntry]] = defaultdict(list)
    new_groups: dict[tuple[object, ...], list[SnapshotEntry]] = defaultdict(list)
    for entry in deleted:
        key = _rename_key(entry, config.require_equal_mode_for_rename)
        if key is not None:
            old_groups[key].append(entry)
    for entry in created:
        key = _rename_key(entry, config.require_equal_mode_for_rename)
        if key is not None:
            new_groups[key].append(entry)

    used_old: set[str] = set()
    used_new: set[str] = set()
    renames: list[WorkspaceChange] = []
    for key in sorted(set(old_groups) & set(new_groups), key=repr):
        olds = sorted(old_groups[key], key=lambda e: e.path)
        news = sorted(new_groups[key], key=lambda e: e.path)
        if max(len(olds), len(news)) > config.max_rename_candidates_per_digest:
            continue
        remaining = list(news)
        for old in olds:
            if not remaining:
                break
            new = min(remaining, key=lambda e: _distance(old.path, e.path))
            remaining.remove(new)
            used_old.add(old.path)
            used_new.add(new.path)
            renames.append(
                WorkspaceChange(
                    WorkspaceChangeKind.RENAMED,
                    new.path,
                    before=old,
                    after=new,
                    old_path=old.path,
                )
            )
    return (
        renames,
        [e for e in deleted if e.path not in used_old],
        [e for e in created if e.path not in used_new],
    )


def _classify(before: SnapshotEntry, after: SnapshotEntry) -> WorkspaceChange | None:
    if before.kind is not after.kind:
        return WorkspaceChange(WorkspaceChangeKind.TYPE_CHANGED, after.path, before, after)
    if before.content_tuple != after.content_tuple:
        return WorkspaceChange(WorkspaceChangeKind.MODIFIED, after.path, before, after)
    if before.mode != after.mode or before.mtime_ns != after.mtime_ns:
        return WorkspaceChange(WorkspaceChangeKind.METADATA_CHANGED, after.path, before, after)
    return None


def _stats(changes: Iterable[WorkspaceChange]) -> ChangeStatistics:
    counts = {kind: 0 for kind in WorkspaceChangeKind}
    added = 0
    removed = 0
    files: set[str] = set()
    directories: set[str] = set()
    symlinks: set[str] = set()
    for change in changes:
        counts[change.kind] += 1
        if change.kind is WorkspaceChangeKind.CREATED:
            added += change.after_size
        elif change.kind is WorkspaceChangeKind.DELETED:
            removed += change.before_size
        else:
            delta = change.byte_delta
            if delta > 0:
                added += delta
            elif delta < 0:
                removed += -delta
        kinds = {e.kind for e in (change.before, change.after) if e is not None}
        if WorkspaceEntryKind.FILE in kinds:
            files.add(change.path)
        if WorkspaceEntryKind.DIRECTORY in kinds:
            directories.add(change.path)
        if WorkspaceEntryKind.SYMLINK in kinds:
            symlinks.add(change.path)
    return ChangeStatistics(
        created=counts[WorkspaceChangeKind.CREATED],
        modified=counts[WorkspaceChangeKind.MODIFIED],
        deleted=counts[WorkspaceChangeKind.DELETED],
        renamed=counts[WorkspaceChangeKind.RENAMED],
        type_changed=counts[WorkspaceChangeKind.TYPE_CHANGED],
        metadata_changed=counts[WorkspaceChangeKind.METADATA_CHANGED],
        bytes_added=added,
        bytes_removed=removed,
        touched_files=len(files),
        touched_directories=len(directories),
        touched_symlinks=len(symlinks),
    )


class WorkspaceDiffer:
    def __init__(self, config: DiffConfig | None = None) -> None:
        self.config = config or DiffConfig()

    def diff(self, before: WorkspaceSnapshot, after: WorkspaceSnapshot) -> ChangeSet:
        if before.root_fingerprint != after.root_fingerprint:
            raise ValueError("snapshot roots differ")
        old = dict(before.by_path)
        new = dict(after.by_path)
        changes: list[WorkspaceChange] = []
        for path in sorted(set(old) & set(new)):
            change = _classify(old[path], new[path])
            if change is not None:
                changes.append(change)
        deleted = [old[p] for p in sorted(set(old) - set(new))]
        created = [new[p] for p in sorted(set(new) - set(old))]
        renames, deleted, created = _pair_renames(deleted, created, self.config)
        changes.extend(renames)
        changes.extend(
            WorkspaceChange(WorkspaceChangeKind.DELETED, entry.path, before=entry)
            for entry in deleted
        )
        changes.extend(
            WorkspaceChange(WorkspaceChangeKind.CREATED, entry.path, after=entry)
            for entry in created
        )
        changes.sort(key=lambda c: (c.path, c.kind.value, c.old_path))
        frozen = tuple(changes)
        digest = hashlib.sha256(
            canonical_json(
                {
                    "before": before.digest,
                    "after": after.digest,
                    "changes": [c.to_dict() for c in frozen],
                }
            )
        ).hexdigest()
        return ChangeSet(
            before.snapshot_id,
            after.snapshot_id,
            frozen,
            _stats(frozen),
            digest,
        )
