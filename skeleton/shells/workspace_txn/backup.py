"""Content-addressed pre-mutation backups for guarded rollback."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Iterable
import uuid

from skeleton.shells.provenance import canonical_json
from skeleton.shells.workspace_txn.pathing import lexical_join_under_root, root_fingerprint
from skeleton.shells.workspace_txn.types import (
    BackupManifest,
    BackupRecord,
    SnapshotEntry,
    WorkspaceEntryKind,
    WorkspaceSnapshot,
)


class BackupError(RuntimeError):
    pass


class ContentAddressedBackupStore:
    def __init__(
        self,
        storage_root: Path | str,
        *,
        max_total_bytes: int = 2 * 1024 * 1024 * 1024,
        max_blob_bytes: int = 128 * 1024 * 1024,
    ) -> None:
        self.storage_root = Path(storage_root).expanduser()
        self.max_total_bytes = max_total_bytes
        self.max_blob_bytes = max_blob_bytes
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in (max_total_bytes, max_blob_bytes)
        ):
            raise ValueError("backup bounds must be positive integers")
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.blob_root = self.storage_root / "blobs"
        self.manifest_root = self.storage_root / "manifests"
        self.blob_root.mkdir(exist_ok=True)
        self.manifest_root.mkdir(exist_ok=True)

    def require_external_to_workspace(self, workspace_root: Path | str) -> None:
        """Reject backup storage nested inside the workspace being protected."""

        root = Path(workspace_root).expanduser().resolve(strict=True)
        storage = self.storage_root.resolve(strict=True)
        if storage == root or root in storage.parents:
            raise BackupError(
                "backup storage must be outside the protected workspace"
            )

    def _blob_path(self, digest: str) -> Path:
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise BackupError("invalid backup digest")
        shard = self.blob_root / digest[:2]
        shard.mkdir(exist_ok=True)
        return shard / digest[2:]

    def _read_verified(self, path: Path, expected: SnapshotEntry) -> bytes:
        if expected.kind is not WorkspaceEntryKind.FILE:
            raise BackupError("only files have backup bytes")
        if expected.size > self.max_blob_bytes:
            raise BackupError("backup file exceeds per-blob bound")
        try:
            metadata = path.lstat()
        except OSError as exc:
            raise BackupError("backup source unavailable") from exc
        if not stat.S_ISREG(metadata.st_mode):
            raise BackupError("backup source changed type")
        if int(metadata.st_size) != expected.size:
            raise BackupError("backup source changed size")
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise BackupError("failed reading backup source") from exc
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected.digest:
            raise BackupError("backup source digest no longer matches snapshot")
        return data

    def put_blob(self, digest: str, data: bytes) -> str:
        actual = hashlib.sha256(data).hexdigest()
        if actual != digest:
            raise BackupError("blob digest mismatch")
        if len(data) > self.max_blob_bytes:
            raise BackupError("blob exceeds backup bound")
        destination = self._blob_path(digest)
        if destination.exists():
            if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
                raise BackupError("existing backup blob is corrupt")
            return str(destination.relative_to(self.storage_root))
        fd, temporary = tempfile.mkstemp(prefix=".backup-", dir=str(destination.parent))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
        return str(destination.relative_to(self.storage_root))

    def read_blob(self, record: BackupRecord) -> bytes:
        if record.kind is not WorkspaceEntryKind.FILE:
            raise BackupError("backup record has no file payload")
        if len(record.digest) != 64 or any(
            c not in "0123456789abcdef" for c in record.digest
        ):
            raise BackupError("backup record digest is invalid")
        expected_key = str(
            Path("blobs") / record.digest[:2] / record.digest[2:]
        )
        if record.storage_key != expected_key:
            raise BackupError("backup storage key does not match digest")
        path = self.storage_root / expected_key
        try:
            metadata = path.lstat()
        except OSError as exc:
            raise BackupError("backup blob unavailable") from exc
        if not stat.S_ISREG(metadata.st_mode):
            raise BackupError("backup blob is not a regular file")
        if int(metadata.st_size) != record.size:
            raise BackupError("backup blob size does not match manifest")
        if int(metadata.st_size) > self.max_blob_bytes:
            raise BackupError("backup blob exceeds configured bound")
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise BackupError("backup blob unavailable") from exc
        if hashlib.sha256(data).hexdigest() != record.digest:
            raise BackupError("backup blob verification failed")
        return data

    def _publish_manifest(self, manifest: BackupManifest) -> None:
        destination = self.manifest_root / f"{manifest.backup_id}.json"
        payload = json.dumps(
            manifest.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        fd, temporary = tempfile.mkstemp(
            prefix=".manifest-",
            suffix=".tmp",
            dir=str(self.manifest_root),
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
            # Best-effort directory fsync closes the rename durability window
            # on filesystems that support syncing directory metadata.
            try:
                directory_fd = os.open(self.manifest_root, os.O_RDONLY)
            except OSError:
                directory_fd = None
            if directory_fd is not None:
                try:
                    os.fsync(directory_fd)
                except OSError:
                    pass
                finally:
                    os.close(directory_fd)
        except OSError as exc:
            raise BackupError("failed publishing backup manifest") from exc
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            except OSError:
                pass

    def create_manifest(
        self,
        workspace_root: Path | str,
        snapshot: WorkspaceSnapshot,
        *,
        paths: Iterable[str] | None = None,
    ) -> BackupManifest:
        root = Path(workspace_root).expanduser().resolve(strict=True)
        if root_fingerprint(root) != snapshot.root_fingerprint:
            raise BackupError("snapshot belongs to another workspace root")
        selected = set(paths) if paths is not None else None
        records: list[BackupRecord] = []
        total = 0
        for entry in snapshot.entries:
            if selected is not None and entry.path not in selected:
                continue
            absolute = lexical_join_under_root(root, entry.path)
            if entry.kind is WorkspaceEntryKind.FILE:
                data = self._read_verified(absolute, entry)
                total += len(data)
                if total > self.max_total_bytes:
                    raise BackupError("backup byte budget exceeded")
                key = self.put_blob(entry.digest, data)
                records.append(
                    BackupRecord(
                        entry.path,
                        entry.kind,
                        entry.digest,
                        key,
                        entry.size,
                        entry.mode,
                        entry.mtime_ns,
                    )
                )
            elif entry.kind is WorkspaceEntryKind.SYMLINK:
                try:
                    target = os.readlink(absolute)
                except OSError as exc:
                    raise BackupError("failed reading backup symlink") from exc
                if os.fsdecode(target) != entry.link_target:
                    raise BackupError("symlink changed after snapshot")
                records.append(
                    BackupRecord(
                        entry.path,
                        entry.kind,
                        "",
                        "",
                        entry.size,
                        entry.mode,
                        entry.mtime_ns,
                        link_target=entry.link_target,
                    )
                )
            elif entry.kind is WorkspaceEntryKind.DIRECTORY:
                records.append(
                    BackupRecord(
                        entry.path,
                        entry.kind,
                        "",
                        "",
                        0,
                        entry.mode,
                        entry.mtime_ns,
                    )
                )
        records.sort(key=lambda record: record.path)
        try:
            root_metadata = root.stat()
        except OSError as exc:
            raise BackupError("failed reading workspace root metadata") from exc
        root_mode = stat.S_IMODE(root_metadata.st_mode)
        root_mtime_ns = int(root_metadata.st_mtime_ns)
        unsigned_manifest = BackupManifest(
            uuid.uuid4().hex,
            snapshot.root_fingerprint,
            datetime.now(timezone.utc).isoformat(),
            tuple(records),
            total,
            "",
            root_mode=root_mode,
            root_mtime_ns=root_mtime_ns,
        )
        digest = hashlib.sha256(
            canonical_json(unsigned_manifest.integrity_payload())
        ).hexdigest()
        manifest = BackupManifest(
            unsigned_manifest.backup_id,
            unsigned_manifest.root_fingerprint,
            unsigned_manifest.created_at,
            unsigned_manifest.records,
            unsigned_manifest.total_bytes,
            digest,
            root_mode=root_mode,
            root_mtime_ns=root_mtime_ns,
        )
        self._publish_manifest(manifest)
        return manifest

    def verify_manifest(self, manifest: BackupManifest) -> bool:
        expected = hashlib.sha256(
            canonical_json(manifest.integrity_payload())
        ).hexdigest()
        if expected != manifest.digest:
            return False
        for record in manifest.records:
            if record.kind is WorkspaceEntryKind.FILE:
                try:
                    self.read_blob(record)
                except BackupError:
                    return False
        return True

    def has_blob(self, digest: str) -> bool:
        path = self._blob_path(digest)
        return path.exists() and path.is_file()

    def delete_manifest(self, backup_id: str) -> bool:
        if not backup_id or "/" in backup_id or "\\" in backup_id:
            raise BackupError("invalid backup id")
        path = self.manifest_root / f"{backup_id}.json"
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False

    def blob_count(self) -> int:
        count = 0
        for shard in self.blob_root.iterdir():
            if not shard.is_dir():
                continue
            count += sum(1 for item in shard.iterdir() if item.is_file())
        return count
