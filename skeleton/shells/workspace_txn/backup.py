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
        path = self.storage_root / record.storage_key
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise BackupError("backup blob unavailable") from exc
        if hashlib.sha256(data).hexdigest() != record.digest:
            raise BackupError("backup blob verification failed")
        return data

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
                    )
                )
        records.sort(key=lambda record: record.path)
        payload = {
            "root_fingerprint": snapshot.root_fingerprint,
            "records": [record.to_dict() for record in records],
            "total_bytes": total,
        }
        digest = hashlib.sha256(canonical_json(payload)).hexdigest()
        manifest = BackupManifest(
            uuid.uuid4().hex,
            snapshot.root_fingerprint,
            datetime.now(timezone.utc).isoformat(),
            tuple(records),
            total,
            digest,
        )
        manifest_path = self.manifest_root / f"{manifest.backup_id}.json"
        manifest_path.write_text(
            json.dumps(manifest.to_dict(), sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        return manifest

    def verify_manifest(self, manifest: BackupManifest) -> bool:
        payload = {
            "root_fingerprint": manifest.root_fingerprint,
            "records": [record.to_dict() for record in manifest.records],
            "total_bytes": manifest.total_bytes,
        }
        expected = hashlib.sha256(canonical_json(payload)).hexdigest()
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
