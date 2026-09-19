"""Typed records for bounded workspace mutation transactions.

This package adds a change-observation and recovery plane around ShellExecutor.
It never starts a process itself; execution remains owned by the established
policy-bound shell executor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class WorkspaceEntryKind(str, Enum):
    FILE = "file"
    DIRECTORY = "directory"
    SYMLINK = "symlink"
    OTHER = "other"


class WorkspaceChangeKind(str, Enum):
    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"
    TYPE_CHANGED = "type_changed"
    METADATA_CHANGED = "metadata_changed"


class WorkspaceTransactionState(str, Enum):
    CREATED = "created"
    LEASED = "leased"
    SNAPSHOTTING = "snapshotting"
    BACKING_UP = "backing_up"
    EXECUTING = "executing"
    REVIEWING = "reviewing"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    ROLLBACK_FAILED = "rollback_failed"
    ABORTED = "aborted"


class RollbackActionKind(str, Enum):
    REMOVE_CREATED = "remove_created"
    RESTORE_MODIFIED = "restore_modified"
    RESTORE_DELETED = "restore_deleted"
    RESTORE_METADATA = "restore_metadata"
    REVERSE_RENAME = "reverse_rename"
    REMOVE_CREATED_DIRECTORY = "remove_created_directory"
    RESTORE_DIRECTORY = "restore_directory"


class RollbackActionState(str, Enum):
    PLANNED = "planned"
    APPLIED = "applied"
    SKIPPED = "skipped"
    CONFLICT = "conflict"
    FAILED = "failed"


@dataclass(frozen=True)
class ScanLimits:
    max_entries: int = 200_000
    max_file_bytes: int = 128 * 1024 * 1024
    max_total_hashed_bytes: int = 2 * 1024 * 1024 * 1024
    max_path_bytes: int = 4096
    max_depth: int = 64
    hash_chunk_bytes: int = 1024 * 1024
    include_directories: bool = True
    include_symlinks: bool = True
    include_other: bool = False

    def __post_init__(self) -> None:
        for name in (
            "max_entries",
            "max_file_bytes",
            "max_total_hashed_bytes",
            "max_path_bytes",
            "max_depth",
            "hash_chunk_bytes",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True)
class SnapshotEntry:
    path: str
    kind: WorkspaceEntryKind
    size: int
    mode: int
    mtime_ns: int
    digest: str = ""
    link_target: str = ""
    device: int = 0
    inode: int = 0

    def __post_init__(self) -> None:
        if not self.path or self.path.startswith("/") or self.path.startswith("../"):
            raise ValueError("snapshot path must be a non-empty relative path")
        if "\\" in self.path:
            raise ValueError("snapshot path must use POSIX separators")
        if isinstance(self.size, bool) or not isinstance(self.size, int) or self.size < 0:
            raise ValueError("entry size must be a non-negative integer")
        if isinstance(self.mode, bool) or not isinstance(self.mode, int) or self.mode < 0:
            raise ValueError("entry mode must be a non-negative integer")
        if isinstance(self.mtime_ns, bool) or not isinstance(self.mtime_ns, int) or self.mtime_ns < 0:
            raise ValueError("entry mtime_ns must be a non-negative integer")
        if self.digest and len(self.digest) != 64:
            raise ValueError("entry digest must be SHA-256 hex")
        if self.kind is WorkspaceEntryKind.FILE and not self.digest:
            raise ValueError("regular files require a content digest")
        if self.kind is WorkspaceEntryKind.SYMLINK and not self.link_target:
            raise ValueError("symlink entries require a link target")

    @property
    def identity_tuple(self) -> tuple[Any, ...]:
        return (
            self.kind.value,
            self.size,
            self.mode,
            self.mtime_ns,
            self.digest,
            self.link_target,
        )

    @property
    def content_tuple(self) -> tuple[Any, ...]:
        return (
            self.kind.value,
            self.size,
            self.digest,
            self.link_target,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "kind": self.kind.value,
            "size": self.size,
            "mode": self.mode,
            "mtime_ns": self.mtime_ns,
            "digest": self.digest,
            "link_target": self.link_target,
            "device": self.device,
            "inode": self.inode,
        }


@dataclass(frozen=True)
class ScanStatistics:
    files: int = 0
    directories: int = 0
    symlinks: int = 0
    other: int = 0
    hashed_bytes: int = 0
    skipped_bytes: int = 0
    errors: int = 0

    def __post_init__(self) -> None:
        for name in (
            "files",
            "directories",
            "symlinks",
            "other",
            "hashed_bytes",
            "skipped_bytes",
            "errors",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be non-negative")

    @property
    def entries(self) -> int:
        return self.files + self.directories + self.symlinks + self.other

    def to_dict(self) -> dict[str, int]:
        return {
            "files": self.files,
            "directories": self.directories,
            "symlinks": self.symlinks,
            "other": self.other,
            "hashed_bytes": self.hashed_bytes,
            "skipped_bytes": self.skipped_bytes,
            "errors": self.errors,
            "entries": self.entries,
        }


@dataclass(frozen=True)
class WorkspaceSnapshot:
    root_fingerprint: str
    created_at: str
    snapshot_id: str
    entries: tuple[SnapshotEntry, ...]
    statistics: ScanStatistics
    digest: str
    excluded_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if len(self.root_fingerprint) != 64:
            raise ValueError("root_fingerprint must be SHA-256 hex")
        if not self.snapshot_id:
            raise ValueError("snapshot_id is required")
        if len(self.digest) != 64:
            raise ValueError("snapshot digest must be SHA-256 hex")
        paths = [entry.path for entry in self.entries]
        if paths != sorted(paths):
            raise ValueError("snapshot entries must be sorted")
        if len(paths) != len(set(paths)):
            raise ValueError("snapshot paths must be unique")

    @property
    def by_path(self) -> Mapping[str, SnapshotEntry]:
        return MappingProxyType({entry.path: entry for entry in self.entries})

    def get(self, path: str) -> SnapshotEntry | None:
        return self.by_path.get(path)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_fingerprint": self.root_fingerprint,
            "created_at": self.created_at,
            "snapshot_id": self.snapshot_id,
            "entries": [entry.to_dict() for entry in self.entries],
            "statistics": self.statistics.to_dict(),
            "digest": self.digest,
            "excluded_paths": list(self.excluded_paths),
        }


@dataclass(frozen=True)
class WorkspaceChange:
    kind: WorkspaceChangeKind
    path: str
    before: SnapshotEntry | None = None
    after: SnapshotEntry | None = None
    old_path: str = ""

    def __post_init__(self) -> None:
        if not self.path:
            raise ValueError("change path is required")
        if self.kind is WorkspaceChangeKind.CREATED:
            if self.before is not None or self.after is None:
                raise ValueError("created change requires only after")
        elif self.kind is WorkspaceChangeKind.DELETED:
            if self.before is None or self.after is not None:
                raise ValueError("deleted change requires only before")
        elif self.kind is WorkspaceChangeKind.RENAMED:
            if self.before is None or self.after is None or not self.old_path:
                raise ValueError("renamed change requires before/after/old_path")
        elif self.before is None or self.after is None:
            raise ValueError("change requires before and after")

    @property
    def before_size(self) -> int:
        return 0 if self.before is None else self.before.size

    @property
    def after_size(self) -> int:
        return 0 if self.after is None else self.after.size

    @property
    def byte_delta(self) -> int:
        return self.after_size - self.before_size

    @property
    def is_content_change(self) -> bool:
        if self.kind in {
            WorkspaceChangeKind.CREATED,
            WorkspaceChangeKind.DELETED,
            WorkspaceChangeKind.RENAMED,
            WorkspaceChangeKind.TYPE_CHANGED,
        }:
            return True
        assert self.before is not None and self.after is not None
        return self.before.content_tuple != self.after.content_tuple

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "path": self.path,
            "old_path": self.old_path,
            "byte_delta": self.byte_delta,
            "before": None if self.before is None else self.before.to_dict(),
            "after": None if self.after is None else self.after.to_dict(),
        }


@dataclass(frozen=True)
class ChangeStatistics:
    created: int = 0
    modified: int = 0
    deleted: int = 0
    renamed: int = 0
    type_changed: int = 0
    metadata_changed: int = 0
    bytes_added: int = 0
    bytes_removed: int = 0
    touched_files: int = 0
    touched_directories: int = 0
    touched_symlinks: int = 0

    @property
    def total_changes(self) -> int:
        return (
            self.created
            + self.modified
            + self.deleted
            + self.renamed
            + self.type_changed
            + self.metadata_changed
        )

    @property
    def net_bytes(self) -> int:
        return self.bytes_added - self.bytes_removed

    def to_dict(self) -> dict[str, int]:
        return {
            "created": self.created,
            "modified": self.modified,
            "deleted": self.deleted,
            "renamed": self.renamed,
            "type_changed": self.type_changed,
            "metadata_changed": self.metadata_changed,
            "bytes_added": self.bytes_added,
            "bytes_removed": self.bytes_removed,
            "net_bytes": self.net_bytes,
            "touched_files": self.touched_files,
            "touched_directories": self.touched_directories,
            "touched_symlinks": self.touched_symlinks,
            "total_changes": self.total_changes,
        }


@dataclass(frozen=True)
class ChangeSet:
    before_snapshot_id: str
    after_snapshot_id: str
    changes: tuple[WorkspaceChange, ...]
    statistics: ChangeStatistics
    digest: str

    def __post_init__(self) -> None:
        if not self.before_snapshot_id or not self.after_snapshot_id:
            raise ValueError("snapshot identities are required")
        if len(self.digest) != 64:
            raise ValueError("change-set digest must be SHA-256 hex")
        keys = [(c.path, c.kind.value, c.old_path) for c in self.changes]
        if keys != sorted(keys):
            raise ValueError("changes must be deterministically sorted")

    @property
    def empty(self) -> bool:
        return not self.changes

    def paths(self) -> tuple[str, ...]:
        return tuple(change.path for change in self.changes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "before_snapshot_id": self.before_snapshot_id,
            "after_snapshot_id": self.after_snapshot_id,
            "changes": [change.to_dict() for change in self.changes],
            "statistics": self.statistics.to_dict(),
            "digest": self.digest,
        }


@dataclass(frozen=True)
class PolicyViolation:
    code: str
    path: str
    detail: str
    severity: str = "error"

    def __post_init__(self) -> None:
        if not self.code:
            raise ValueError("violation code is required")
        if self.severity not in {"warning", "error", "critical"}:
            raise ValueError("invalid severity")

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "path": self.path,
            "detail": self.detail,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class MutationDecision:
    allowed: bool
    violations: tuple[PolicyViolation, ...]
    change_set_digest: str
    policy_digest: str

    def __post_init__(self) -> None:
        if self.allowed and any(v.severity in {"error", "critical"} for v in self.violations):
            raise ValueError("allowed decision cannot contain blocking violations")
        if len(self.change_set_digest) != 64 or len(self.policy_digest) != 64:
            raise ValueError("decision digests must be SHA-256 hex")

    @property
    def blocking(self) -> tuple[PolicyViolation, ...]:
        return tuple(v for v in self.violations if v.severity in {"error", "critical"})

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "violations": [v.to_dict() for v in self.violations],
            "change_set_digest": self.change_set_digest,
            "policy_digest": self.policy_digest,
        }


@dataclass(frozen=True)
class BackupRecord:
    path: str
    kind: WorkspaceEntryKind
    digest: str
    storage_key: str
    size: int
    mode: int
    mtime_ns: int = 0
    link_target: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "kind": self.kind.value,
            "digest": self.digest,
            "storage_key": self.storage_key,
            "size": self.size,
            "mode": self.mode,
            "mtime_ns": self.mtime_ns,
            "link_target": self.link_target,
        }


@dataclass(frozen=True)
class BackupManifest:
    backup_id: str
    root_fingerprint: str
    created_at: str
    records: tuple[BackupRecord, ...]
    total_bytes: int
    digest: str
    root_mode: int | None = None
    root_mtime_ns: int | None = None
    snapshot_digest: str = ""
    complete_snapshot: bool = False

    def __post_init__(self) -> None:
        if (self.root_mode is None) != (self.root_mtime_ns is None):
            raise ValueError("root metadata must be complete or absent")
        if self.root_mode is not None:
            if (
                isinstance(self.root_mode, bool)
                or not isinstance(self.root_mode, int)
                or self.root_mode < 0
            ):
                raise ValueError("root_mode must be a non-negative integer")
            if (
                isinstance(self.root_mtime_ns, bool)
                or not isinstance(self.root_mtime_ns, int)
                or self.root_mtime_ns < 0
            ):
                raise ValueError("root_mtime_ns must be a non-negative integer")
        if self.snapshot_digest and len(self.snapshot_digest) != 64:
            raise ValueError("snapshot_digest must be SHA-256 hex")
        if not isinstance(self.complete_snapshot, bool):
            raise ValueError("complete_snapshot must be boolean")
        if self.complete_snapshot and not self.snapshot_digest:
            raise ValueError("complete backup requires snapshot_digest")

    @property
    def by_path(self) -> Mapping[str, BackupRecord]:
        return MappingProxyType({r.path: r for r in self.records})

    def integrity_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "root_fingerprint": self.root_fingerprint,
            "records": [r.to_dict() for r in self.records],
            "total_bytes": self.total_bytes,
        }
        if self.root_mode is not None and self.root_mtime_ns is not None:
            payload["root_metadata"] = {
                "mode": self.root_mode,
                "mtime_ns": self.root_mtime_ns,
            }
        if self.snapshot_digest:
            payload["snapshot"] = {
                "digest": self.snapshot_digest,
                "complete": self.complete_snapshot,
            }
        return payload

    def to_dict(self) -> dict[str, Any]:
        value = {
            "backup_id": self.backup_id,
            "root_fingerprint": self.root_fingerprint,
            "created_at": self.created_at,
            "records": [r.to_dict() for r in self.records],
            "total_bytes": self.total_bytes,
            "digest": self.digest,
        }
        if self.root_mode is not None and self.root_mtime_ns is not None:
            value["root_mode"] = self.root_mode
            value["root_mtime_ns"] = self.root_mtime_ns
        if self.snapshot_digest:
            value["snapshot_digest"] = self.snapshot_digest
            value["complete_snapshot"] = self.complete_snapshot
        return value


@dataclass(frozen=True)
class RollbackAction:
    kind: RollbackActionKind
    path: str
    source_path: str = ""
    expected_digest: str = ""
    restore_digest: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind.value,
            "path": self.path,
            "source_path": self.source_path,
            "expected_digest": self.expected_digest,
            "restore_digest": self.restore_digest,
        }


@dataclass(frozen=True)
class RollbackActionResult:
    action: RollbackAction
    state: RollbackActionState
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.to_dict(),
            "state": self.state.value,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class RollbackReport:
    started_at: str
    finished_at: str
    actions: tuple[RollbackActionResult, ...]
    verified: bool
    before_snapshot_digest: str
    final_snapshot_digest: str

    @property
    def ok(self) -> bool:
        return self.verified and all(
            a.state in {RollbackActionState.APPLIED, RollbackActionState.SKIPPED}
            for a in self.actions
        )

    @property
    def conflicts(self) -> tuple[RollbackActionResult, ...]:
        return tuple(a for a in self.actions if a.state is RollbackActionState.CONFLICT)

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "actions": [a.to_dict() for a in self.actions],
            "verified": self.verified,
            "ok": self.ok,
            "before_snapshot_digest": self.before_snapshot_digest,
            "final_snapshot_digest": self.final_snapshot_digest,
        }


@dataclass(frozen=True)
class TransactionReceipt:
    transaction_id: str
    correlation_id: str
    state: WorkspaceTransactionState
    command_fingerprint: str
    before_snapshot_digest: str
    after_snapshot_digest: str
    change_set_digest: str
    policy_digest: str
    policy_allowed: bool
    execution_ok: bool
    rolled_back: bool
    rollback_ok: bool | None
    started_at: str
    finished_at: str
    execution_receipt_ids: tuple[str, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)
    receipt_digest: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def payload(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "correlation_id": self.correlation_id,
            "state": self.state.value,
            "command_fingerprint": self.command_fingerprint,
            "before_snapshot_digest": self.before_snapshot_digest,
            "after_snapshot_digest": self.after_snapshot_digest,
            "change_set_digest": self.change_set_digest,
            "policy_digest": self.policy_digest,
            "policy_allowed": self.policy_allowed,
            "execution_ok": self.execution_ok,
            "rolled_back": self.rolled_back,
            "rollback_ok": self.rollback_ok,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "execution_receipt_ids": list(self.execution_receipt_ids),
            "metadata": dict(self.metadata),
        }

    def to_dict(self) -> dict[str, Any]:
        value = self.payload()
        value["receipt_digest"] = self.receipt_digest
        return value


@dataclass(frozen=True)
class TransactionResult:
    receipt: TransactionReceipt
    before: WorkspaceSnapshot
    after: WorkspaceSnapshot
    changes: ChangeSet
    decision: MutationDecision
    execution: Any
    rollback: RollbackReport | None = None
    backup: BackupManifest | None = None

    @property
    def accepted(self) -> bool:
        return self.receipt.state is WorkspaceTransactionState.ACCEPTED

    @property
    def reverted(self) -> bool:
        return self.receipt.state is WorkspaceTransactionState.ROLLED_BACK

    def to_dict(self, *, include_snapshots: bool = False) -> dict[str, Any]:
        value: dict[str, Any] = {
            "receipt": self.receipt.to_dict(),
            "changes": self.changes.to_dict(),
            "decision": self.decision.to_dict(),
            "rollback": None if self.rollback is None else self.rollback.to_dict(),
            "backup": None if self.backup is None else self.backup.to_dict(),
        }
        if include_snapshots:
            value["before"] = self.before.to_dict()
            value["after"] = self.after.to_dict()
        return value
