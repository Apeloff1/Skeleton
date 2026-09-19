"""Conflict-aware rollback for workspace transactions."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import stat
import tempfile

from skeleton.shells.workspace_txn.backup import BackupError, ContentAddressedBackupStore
from skeleton.shells.workspace_txn.pathing import lexical_join_under_root
from skeleton.shells.workspace_txn.scanner import WorkspaceScanner
from skeleton.shells.workspace_txn.types import (
    BackupManifest,
    ChangeSet,
    RollbackAction,
    RollbackActionKind,
    RollbackActionResult,
    RollbackActionState,
    RollbackReport,
    WorkspaceChangeKind,
    WorkspaceEntryKind,
    WorkspaceSnapshot,
)


class RollbackError(RuntimeError):
    pass


def build_rollback_actions(changes: ChangeSet) -> tuple[RollbackAction, ...]:
    actions: list[RollbackAction] = []
    for change in changes.changes:
        before_digest = "" if change.before is None else change.before.digest
        after_digest = "" if change.after is None else change.after.digest
        if change.kind is WorkspaceChangeKind.CREATED:
            kind = (
                RollbackActionKind.REMOVE_CREATED_DIRECTORY
                if change.after is not None and change.after.kind is WorkspaceEntryKind.DIRECTORY
                else RollbackActionKind.REMOVE_CREATED
            )
            actions.append(
                RollbackAction(
                    kind,
                    change.path,
                    expected_digest=after_digest,
                )
            )
        elif change.kind is WorkspaceChangeKind.DELETED:
            kind = (
                RollbackActionKind.RESTORE_DIRECTORY
                if change.before is not None and change.before.kind is WorkspaceEntryKind.DIRECTORY
                else RollbackActionKind.RESTORE_DELETED
            )
            actions.append(
                RollbackAction(
                    kind,
                    change.path,
                    restore_digest=before_digest,
                )
            )
        elif change.kind is WorkspaceChangeKind.RENAMED:
            actions.append(
                RollbackAction(
                    RollbackActionKind.REVERSE_RENAME,
                    change.path,
                    source_path=change.old_path,
                    expected_digest=after_digest,
                    restore_digest=before_digest,
                )
            )
        elif change.kind in {WorkspaceChangeKind.MODIFIED, WorkspaceChangeKind.TYPE_CHANGED}:
            actions.append(
                RollbackAction(
                    RollbackActionKind.RESTORE_MODIFIED,
                    change.path,
                    expected_digest=after_digest,
                    restore_digest=before_digest,
                )
            )
        elif change.kind is WorkspaceChangeKind.METADATA_CHANGED:
            actions.append(
                RollbackAction(
                    RollbackActionKind.RESTORE_METADATA,
                    change.path,
                    expected_digest=after_digest,
                    restore_digest=before_digest,
                )
            )
    actions.sort(key=lambda action: (-action.path.count("/"), action.path, action.kind.value))
    return tuple(actions)


def build_directory_metadata_actions(
    changes: ChangeSet,
    manifest: BackupManifest,
) -> tuple[RollbackAction, ...]:
    """Restore pre-existing directory metadata after all structural rollback.

    Creating, deleting, restoring, or renaming a child updates its parent
    directory mtime.  Directory metadata therefore cannot be restored reliably
    in the same pass as structural actions: a later child operation may dirty
    the parent again.  Build a final metadata pass for every backed-up
    directory that contains an affected path, even when the original snapshot
    diff did not independently classify the directory as metadata-changed.
    """

    affected: set[str] = set()
    for change in changes.changes:
        affected.add(change.path)
        if change.old_path:
            affected.add(change.old_path)

    actions: list[RollbackAction] = []
    for record in manifest.records:
        if record.kind is not WorkspaceEntryKind.DIRECTORY:
            continue
        prefix = record.path.rstrip("/") + "/"
        if not any(path == record.path or path.startswith(prefix) for path in affected):
            continue
        actions.append(
            RollbackAction(
                RollbackActionKind.RESTORE_METADATA,
                record.path,
                restore_digest=record.digest,
            )
        )

    # Deepest directories first and shallowest last.  This leaves the outermost
    # affected directory as the final filesystem metadata write in its subtree.
    actions.sort(key=lambda action: (-action.path.count("/"), action.path))
    return tuple(actions)


class WorkspaceRollback:
    def __init__(
        self,
        scanner: WorkspaceScanner,
        backup_store: ContentAddressedBackupStore,
    ) -> None:
        self.scanner = scanner
        self.backup_store = backup_store

    def _current(self, root: Path, path: str):
        entries = self.scanner.rescan_paths(root, (path,))
        return entries[0] if entries else None

    @staticmethod
    def _remove_path(path: Path) -> None:
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            return
        if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
            path.rmdir()
        else:
            path.unlink()

    @staticmethod
    def _ensure_parent(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _restore_metadata(
        path: Path,
        record,
        *,
        symlink: bool = False,
    ) -> None:
        if not symlink:
            os.chmod(path, record.mode)
        try:
            os.utime(
                path,
                ns=(record.mtime_ns, record.mtime_ns),
                follow_symlinks=not symlink,
            )
        except (NotImplementedError, OSError):
            if not symlink:
                raise

    @staticmethod
    def _restore_root_metadata(
        root: Path,
        manifest: BackupManifest,
    ) -> RollbackActionResult | None:
        if manifest.root_mode is None or manifest.root_mtime_ns is None:
            return None
        action = RollbackAction(
            RollbackActionKind.RESTORE_METADATA,
            ".",
        )
        try:
            os.chmod(root, manifest.root_mode)
            os.utime(
                root,
                ns=(manifest.root_mtime_ns, manifest.root_mtime_ns),
            )
        except OSError as exc:
            return RollbackActionResult(
                action,
                RollbackActionState.FAILED,
                str(exc),
            )
        return RollbackActionResult(
            action,
            RollbackActionState.APPLIED,
        )

    def _restore_record(
        self,
        root: Path,
        manifest: BackupManifest,
        path: str,
    ) -> None:
        record = manifest.by_path.get(path)
        if record is None:
            raise RollbackError(f"backup record missing for {path}")
        absolute = lexical_join_under_root(root, path)
        self._ensure_parent(absolute)
        if record.kind is WorkspaceEntryKind.FILE:
            data = self.backup_store.read_blob(record)
            fd, temporary = tempfile.mkstemp(prefix=".rollback-", dir=str(absolute.parent))
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.chmod(temporary, record.mode)
                os.replace(temporary, absolute)
                self._restore_metadata(absolute, record)
            finally:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
            return
        if record.kind is WorkspaceEntryKind.SYMLINK:
            try:
                self._remove_path(absolute)
            except OSError as exc:
                raise RollbackError("failed to replace symlink target") from exc
            os.symlink(record.link_target, absolute)
            self._restore_metadata(absolute, record, symlink=True)
            return
        if record.kind is WorkspaceEntryKind.DIRECTORY:
            absolute.mkdir(parents=True, exist_ok=True)
            self._restore_metadata(absolute, record)
            return
        raise RollbackError("unsupported backup record type")

    def _apply_one(
        self,
        root: Path,
        action: RollbackAction,
        manifest: BackupManifest,
    ) -> RollbackActionResult:
        absolute = lexical_join_under_root(root, action.path)
        current = self._current(root, action.path)

        if action.kind in {
            RollbackActionKind.REMOVE_CREATED,
            RollbackActionKind.REMOVE_CREATED_DIRECTORY,
        }:
            if current is None:
                return RollbackActionResult(
                    action,
                    RollbackActionState.SKIPPED,
                    "created path already absent",
                )
            if action.expected_digest and current.digest != action.expected_digest:
                return RollbackActionResult(
                    action,
                    RollbackActionState.CONFLICT,
                    "created path changed after execution",
                )
            try:
                self._remove_path(absolute)
                return RollbackActionResult(action, RollbackActionState.APPLIED)
            except OSError as exc:
                return RollbackActionResult(action, RollbackActionState.FAILED, str(exc))

        if action.kind is RollbackActionKind.REVERSE_RENAME:
            old = lexical_join_under_root(root, action.source_path)
            record = manifest.by_path.get(action.source_path)
            if record is None:
                return RollbackActionResult(
                    action,
                    RollbackActionState.FAILED,
                    "backup metadata unavailable for rename source",
                )
            if current is None:
                return RollbackActionResult(
                    action,
                    RollbackActionState.CONFLICT,
                    "renamed destination is absent",
                )
            if action.expected_digest and current.digest != action.expected_digest:
                return RollbackActionResult(
                    action,
                    RollbackActionState.CONFLICT,
                    "renamed destination changed",
                )
            if old.exists() or old.is_symlink():
                return RollbackActionResult(
                    action,
                    RollbackActionState.CONFLICT,
                    "rename source was recreated",
                )
            try:
                old.parent.mkdir(parents=True, exist_ok=True)
                os.replace(absolute, old)
                if record.kind is WorkspaceEntryKind.FILE:
                    self._restore_metadata(old, record)
                return RollbackActionResult(action, RollbackActionState.APPLIED)
            except OSError as exc:
                return RollbackActionResult(action, RollbackActionState.FAILED, str(exc))

        if action.kind in {
            RollbackActionKind.RESTORE_MODIFIED,
            RollbackActionKind.RESTORE_DELETED,
            RollbackActionKind.RESTORE_DIRECTORY,
        }:
            if current is not None and action.expected_digest and current.digest != action.expected_digest:
                return RollbackActionResult(
                    action,
                    RollbackActionState.CONFLICT,
                    "path changed after transaction",
                )
            try:
                if current is not None and action.kind is RollbackActionKind.RESTORE_MODIFIED:
                    self._remove_path(absolute)
                self._restore_record(root, manifest, action.path)
                return RollbackActionResult(action, RollbackActionState.APPLIED)
            except (OSError, BackupError, RollbackError) as exc:
                return RollbackActionResult(action, RollbackActionState.FAILED, str(exc))

        if action.kind is RollbackActionKind.RESTORE_METADATA:
            record = manifest.by_path.get(action.path)
            if record is None:
                return RollbackActionResult(
                    action,
                    RollbackActionState.FAILED,
                    "backup metadata unavailable",
                )
            if current is None:
                return RollbackActionResult(
                    action,
                    RollbackActionState.CONFLICT,
                    "path disappeared",
                )
            if action.expected_digest and current.digest != action.expected_digest:
                return RollbackActionResult(
                    action,
                    RollbackActionState.CONFLICT,
                    "content changed after transaction",
                )
            try:
                self._restore_metadata(
                    absolute,
                    record,
                    symlink=current.kind is WorkspaceEntryKind.SYMLINK,
                )
                return RollbackActionResult(action, RollbackActionState.APPLIED)
            except OSError as exc:
                return RollbackActionResult(action, RollbackActionState.FAILED, str(exc))

        return RollbackActionResult(
            action,
            RollbackActionState.FAILED,
            "unknown rollback action",
        )

    def rollback(
        self,
        root: Path | str,
        before: WorkspaceSnapshot,
        changes: ChangeSet,
        manifest: BackupManifest,
    ) -> RollbackReport:
        root_path = Path(root).expanduser().resolve(strict=True)
        started = datetime.now(timezone.utc).isoformat()
        planned = build_rollback_actions(changes)
        directory_paths = {
            action.path
            for action in build_directory_metadata_actions(changes, manifest)
        }
        structural = tuple(
            action
            for action in planned
            if not (
                action.kind is RollbackActionKind.RESTORE_METADATA
                and action.path in directory_paths
            )
        )
        directory_metadata = build_directory_metadata_actions(changes, manifest)

        applied: list[RollbackActionResult] = []
        for action in structural:
            applied.append(self._apply_one(root_path, action, manifest))
        # Directory mtimes/modes are intentionally restored last because every
        # child create/remove/rename can dirty an ancestor directory again.
        for action in directory_metadata:
            applied.append(self._apply_one(root_path, action, manifest))
        root_metadata_result = self._restore_root_metadata(root_path, manifest)
        if root_metadata_result is not None:
            applied.append(root_metadata_result)
        results = tuple(applied)
        final = self.scanner.scan(root_path)
        finished = datetime.now(timezone.utc).isoformat()
        verified = final.digest == before.digest
        if manifest.root_mode is not None and manifest.root_mtime_ns is not None:
            try:
                root_metadata = root_path.stat()
            except OSError:
                verified = False
            else:
                verified = (
                    verified
                    and stat.S_IMODE(root_metadata.st_mode) == manifest.root_mode
                    and int(root_metadata.st_mtime_ns) == manifest.root_mtime_ns
                )
        return RollbackReport(
            started,
            finished,
            results,
            verified,
            before.digest,
            final.digest,
        )
