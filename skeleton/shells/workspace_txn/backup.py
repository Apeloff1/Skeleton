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
from skeleton.shells.workspace_txn.pathing import (
    lexical_join_under_root,
    normalize_relative_path,
    root_fingerprint,
)
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
        max_manifest_bytes: int = 16 * 1024 * 1024,
        max_manifest_records: int = 200_000,
    ) -> None:
        self.storage_root = Path(storage_root).expanduser()
        self.max_total_bytes = max_total_bytes
        self.max_blob_bytes = max_blob_bytes
        self.max_manifest_bytes = max_manifest_bytes
        self.max_manifest_records = max_manifest_records
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in (
                max_total_bytes,
                max_blob_bytes,
                max_manifest_bytes,
                max_manifest_records,
            )
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

    @staticmethod
    def _safe_backup_id(backup_id: str) -> str:
        if (
            not isinstance(backup_id, str)
            or not backup_id
            or len(backup_id) > 128
            or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for ch in backup_id)
        ):
            raise BackupError("invalid backup id")
        return backup_id

    @staticmethod
    def _manifest_int(
        value: object,
        *,
        field: str,
        minimum: int = 0,
    ) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise BackupError(f"invalid manifest integer: {field}")
        return value

    @staticmethod
    def _manifest_hex64(value: object, *, field: str) -> str:
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(ch not in "0123456789abcdef" for ch in value)
        ):
            raise BackupError(f"invalid manifest digest: {field}")
        return value

    def load_manifest(
        self,
        backup_id: str,
        *,
        expected_digest: str | None = None,
        expected_root_fingerprint: str | None = None,
    ) -> BackupManifest:
        """Load persisted rollback evidence with strict structural bounds."""

        safe_id = self._safe_backup_id(backup_id)
        path = self.manifest_root / f"{safe_id}.json"
        try:
            metadata = path.lstat()
        except OSError as exc:
            raise BackupError("backup manifest unavailable") from exc
        if not stat.S_ISREG(metadata.st_mode):
            raise BackupError("backup manifest is not a regular file")
        if int(metadata.st_size) > self.max_manifest_bytes:
            raise BackupError("backup manifest exceeds configured bound")
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise BackupError("failed reading backup manifest") from exc
        if len(raw) != int(metadata.st_size):
            raise BackupError("backup manifest changed while reading")
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BackupError("backup manifest is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise BackupError("backup manifest root must be an object")
        if payload.get("backup_id") != safe_id:
            raise BackupError("backup manifest id mismatch")

        root_fp = self._manifest_hex64(
            payload.get("root_fingerprint"),
            field="root_fingerprint",
        )
        digest = self._manifest_hex64(payload.get("digest"), field="digest")
        if expected_digest is not None and digest != expected_digest:
            raise BackupError("backup manifest digest does not match recovery evidence")
        if (
            expected_root_fingerprint is not None
            and root_fp != expected_root_fingerprint
        ):
            raise BackupError("backup manifest root does not match recovery evidence")

        created_at = payload.get("created_at")
        if not isinstance(created_at, str) or not created_at:
            raise BackupError("backup manifest created_at is invalid")
        total_bytes = self._manifest_int(
            payload.get("total_bytes"),
            field="total_bytes",
        )
        if total_bytes > self.max_total_bytes:
            raise BackupError("backup manifest exceeds total byte budget")

        root_mode_raw = payload.get("root_mode")
        root_mtime_raw = payload.get("root_mtime_ns")
        if (root_mode_raw is None) != (root_mtime_raw is None):
            raise BackupError("backup manifest root metadata is incomplete")
        root_mode = (
            None
            if root_mode_raw is None
            else self._manifest_int(root_mode_raw, field="root_mode")
        )
        root_mtime_ns = (
            None
            if root_mtime_raw is None
            else self._manifest_int(root_mtime_raw, field="root_mtime_ns")
        )

        records_raw = payload.get("records")
        if not isinstance(records_raw, list):
            raise BackupError("backup manifest records must be a list")
        if len(records_raw) > self.max_manifest_records:
            raise BackupError("backup manifest record bound exceeded")

        records: list[BackupRecord] = []
        file_bytes = 0
        previous_path = ""
        for index, item in enumerate(records_raw):
            if not isinstance(item, dict):
                raise BackupError("backup manifest record must be an object")
            raw_path = item.get("path")
            if not isinstance(raw_path, str):
                raise BackupError("backup manifest record path is invalid")
            try:
                normalized = normalize_relative_path(raw_path)
            except ValueError as exc:
                raise BackupError("backup manifest record path is unsafe") from exc
            if normalized != raw_path:
                raise BackupError("backup manifest record path is not canonical")
            if previous_path and normalized <= previous_path:
                raise BackupError("backup manifest records are not strictly sorted")
            previous_path = normalized
            try:
                kind = WorkspaceEntryKind(item.get("kind"))
            except (TypeError, ValueError) as exc:
                raise BackupError("backup manifest record kind is invalid") from exc
            size = self._manifest_int(
                item.get("size"),
                field=f"records[{index}].size",
            )
            mode = self._manifest_int(
                item.get("mode"),
                field=f"records[{index}].mode",
            )
            mtime_ns = self._manifest_int(
                item.get("mtime_ns", 0),
                field=f"records[{index}].mtime_ns",
            )
            record_digest = item.get("digest", "")
            storage_key = item.get("storage_key", "")
            link_target = item.get("link_target", "")
            if not all(
                isinstance(value, str)
                for value in (record_digest, storage_key, link_target)
            ):
                raise BackupError("backup manifest record text field is invalid")

            if kind is WorkspaceEntryKind.FILE:
                record_digest = self._manifest_hex64(
                    record_digest,
                    field=f"records[{index}].digest",
                )
                if size > self.max_blob_bytes:
                    raise BackupError("backup record exceeds per-blob bound")
                expected_key = str(
                    Path("blobs") / record_digest[:2] / record_digest[2:]
                )
                if storage_key != expected_key:
                    raise BackupError("backup storage key does not match digest")
                if link_target:
                    raise BackupError("file backup record cannot contain link target")
                file_bytes += size
                if file_bytes > self.max_total_bytes:
                    raise BackupError("backup record byte budget exceeded")
            elif kind is WorkspaceEntryKind.DIRECTORY:
                if size != 0 or record_digest or storage_key or link_target:
                    raise BackupError("directory backup record has invalid payload")
            elif kind is WorkspaceEntryKind.SYMLINK:
                if record_digest or storage_key:
                    raise BackupError("symlink backup record has invalid payload")
            else:
                raise BackupError("unsupported backup manifest record kind")

            records.append(
                BackupRecord(
                    normalized,
                    kind,
                    record_digest,
                    storage_key,
                    size,
                    mode,
                    mtime_ns,
                    link_target=link_target,
                )
            )

        if file_bytes != total_bytes:
            raise BackupError("backup manifest total byte count is inconsistent")

        manifest = BackupManifest(
            safe_id,
            root_fp,
            created_at,
            tuple(records),
            total_bytes,
            digest,
            root_mode=root_mode,
            root_mtime_ns=root_mtime_ns,
        )
        if not self.verify_manifest(manifest):
            raise BackupError("backup manifest integrity verification failed")
        return manifest

    def delete_manifest(self, backup_id: str) -> bool:
        safe_id = self._safe_backup_id(backup_id)
        path = self.manifest_root / f"{safe_id}.json"
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
