"""Crash-safe, create-only SQLite backup and offline verification for annual work.

Uses SQLite's online backup API so WAL-backed production rows and receipts are
captured in ONE consistent database image, without copying a live .db file.
Snapshot creation and restoration never run workers or renew authority.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
from typing import Any
from urllib.parse import quote

from .annual_production import AnnualProductionStore, SCHEMA, _hash

_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
MAX_BACKUP_BYTES = 4 * 1024**3


class AnnualBackupError(ValueError):
    """A backup image, publication, custody or verification check failed."""


def _private_folder(folder: Path) -> Path:
    if not folder.is_absolute() or not folder.is_dir() or folder.is_symlink():
        raise AnnualBackupError("existing absolute backup directory required")
    if os.name == "posix":
        mode = folder.stat().st_mode
        if mode & 0o077 or folder.stat().st_uid != os.geteuid():
            raise AnnualBackupError("backup directory must be owned and mode 0700")
    return folder


def _sha_file(path: Path) -> tuple[str, int]:
    if path.is_symlink() or not path.is_file():
        raise AnnualBackupError("backup must be a regular, non-symlinked file")
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or not 1 <= before.st_size <= MAX_BACKUP_BYTES:
        raise AnnualBackupError("backup image exceeds bounded read capacity")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    after = path.stat()
    if (size != before.st_size or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns):
        raise AnnualBackupError("backup image changed during verification")
    return digest.hexdigest(), size


def _audit_receipt_chains(db: sqlite3.Connection) -> None:
    """Verify EVERY checkpoint and grant rotation in the immutable snapshot.

    Database structural integrity alone cannot detect altered receipts when a
    copied SQLite file is rewritten and its unkeyed manifest is recomputed.
    This is tamper evidence, not operator authentication or authority renewal.
    """
    producers = db.execute(
        "SELECT production_id, system, sequence, last_receipt_digest, "
        "checkpoint_digest, authority_digest FROM annual_productions ORDER BY production_id"
    )
    for production_id, system, count, tip, checkpoint_tip, authority in producers:
        previous = None
        previous_state = None
        ordinal = 0
        for (sequence, epoch, state, evidence, link, digest) in db.execute(
            "SELECT sequence, epoch, state_digest, evidence_digest, "
            "previous_receipt_digest, receipt_digest "
            "FROM annual_checkpoint_receipts WHERE production_id=? ORDER BY sequence",
            (production_id,),
        ):
            ordinal += 1
            expected = _hash({
                "schema": SCHEMA, "production_id": production_id,
                "system": system, "sequence": sequence,
                "lease_epoch": epoch, "state_digest": state,
                "evidence_digest": evidence, "previous_receipt_digest": link,
            })
            if (type(sequence) is not int or sequence != ordinal
                    or link != previous or digest != expected):
                raise AnnualBackupError("offline production checkpoint chain differs")
            previous = digest
            previous_state = state
        if ordinal != count or tip != previous or checkpoint_tip != previous_state:
            raise AnnualBackupError("offline production checkpoint tip differs")
        previous_rotation = None
        previous_grant = None
        revision = 0
        for (position, old, new, approval, expiry, approved, link, digest) in db.execute(
            "SELECT revision, old_authority_digest, new_authority_digest, "
            "approval_digest, expires_at, approved_at, previous_rotation_digest, "
            "rotation_digest FROM annual_authority_rotations "
            "WHERE production_id=? ORDER BY revision",
            (production_id,),
        ):
            revision += 1
            expected = _hash({
                "schema": SCHEMA, "production_id": production_id,
                "revision": position, "old_authority_digest": old,
                "new_authority_digest": new, "approval_digest": approval,
                "expires_at": expiry, "approved_at": approved,
                "previous_rotation_digest": link,
            })
            if (position != revision or link != previous_rotation
                    or (previous_grant is not None and old != previous_grant)
                    or digest != expected):
                raise AnnualBackupError("offline production authority chain differs")
            previous_grant = new
            previous_rotation = digest
        if previous_grant is not None and authority != previous_grant:
            raise AnnualBackupError("offline production authority head differs")


def _check_database(path: Path) -> dict[str, Any]:
    # Read an immutable snapshot; never try a live WAL sidecar recovery here.
    from urllib.parse import quote
    uri = "file:" + quote(str(path), safe="/") + "?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True, timeout=5) as db:
        integrity = db.execute("PRAGMA integrity_check").fetchone()
        if integrity != ("ok",) or db.execute("PRAGMA foreign_key_check").fetchone():
            raise AnnualBackupError("SQLite image failed integrity or FK validation")
        names = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        expected = {
            "annual_productions", "annual_checkpoint_receipts",
            "annual_authority_rotations",
        }
        if not expected <= names:
            raise AnnualBackupError("required annual production tables are missing")
        counts = {}
        for name in sorted(expected):
            counts[name] = db.execute("SELECT count(*) FROM " + name).fetchone()[0]
        _audit_receipt_chains(db)
    return counts


def verify_annual_snapshot(folder: Path, label: str) -> dict[str, Any]:
    """Check create-only manifest, exact bytes and consistent relational image."""
    folder = _private_folder(Path(folder))
    if not isinstance(label, str) or not _LABEL.fullmatch(label):
        raise AnnualBackupError("invalid backup identity")
    db_file = folder / (label + ".db")
    manifest_file = folder / (label + ".json")
    # An offline, sealed SQLite image MUST NOT have WAL/SHM/journal sidecars.
    # immutable=1 ignores a WAL; silently accepting one would allow a changed
    # logical database to pass verification against the old main-file bytes.
    if any(
        sidecar.exists() or sidecar.is_symlink()
        for sidecar in (
            folder / (label + ".db-wal"),
            folder / (label + ".db-shm"),
            folder / (label + ".db-journal"),
        )
    ):
        raise AnnualBackupError("offline snapshot has unsealed SQLite sidecars")
    if manifest_file.is_symlink() or not manifest_file.is_file():
        raise AnnualBackupError("backup manifest is missing or unsafe")
    if manifest_file.stat().st_size > 8192:
        raise AnnualBackupError("backup manifest exceeds bounded size")
    try:
        manifest = json.loads(manifest_file.read_bytes())
    except (ValueError, UnicodeError) as exc:
        raise AnnualBackupError("backup manifest is invalid") from exc
    if (type(manifest) is not dict or set(manifest) != {
            "schema", "label", "sha256", "bytes", "table_counts"}
            or manifest["schema"] != "skeleton.annual-production.backup.v1"
            or manifest["label"] != label):
        raise AnnualBackupError("backup manifest schema differs")
    digest, size = _sha_file(db_file)
    if digest != manifest["sha256"] or size != manifest["bytes"]:
        raise AnnualBackupError("backup bytes differ from sealed manifest")
    counts = _check_database(db_file)
    if counts != manifest["table_counts"]:
        raise AnnualBackupError("backup table inventory changed")
    return {"verified": True, "label": label, "sha256": digest,
            "bytes": size, "table_counts": counts,
            "worker_execution_or_authority_renewal": False}


def snapshot_annual_production(store: AnnualProductionStore, folder: Path,
                               *, label: str) -> dict[str, Any]:
    """Online snapshot; never overwrite a previous image or manifest.

    A crash can leave an unsealed orphan .db. The label then cannot be reused;
    an operator must reconcile it, rather than silently replacing evidence.
    """
    if not isinstance(store, AnnualProductionStore):
        raise AnnualBackupError("canonical annual production store required")
    folder = _private_folder(Path(folder))
    if not isinstance(label, str) or not _LABEL.fullmatch(label):
        raise AnnualBackupError("invalid backup label")
    target = folder / (label + ".db")
    seal = folder / (label + ".json")
    if any(p.exists() or p.is_symlink() for p in (target, seal)):
        raise AnnualBackupError("backup label already exists; never overwrite")
    fd, temporary = tempfile.mkstemp(prefix=".annual-backup-", suffix=".tmp", dir=folder)
    stage = Path(temporary)
    os.close(fd)
    try:
        with sqlite3.connect(str(store.path), timeout=10) as source:
            with sqlite3.connect(str(stage), timeout=10) as destination:
                source.backup(destination, pages=256, sleep=0.05)
        counts = _check_database(stage)
        digest, size = _sha_file(stage)
        with stage.open("rb") as stream:
            os.fsync(stream.fileno())
        try:
            os.link(stage, target, follow_symlinks=False)
        except FileExistsError as exc:
            raise AnnualBackupError("backup target appeared during publication") from exc
        record = {
            "schema": "skeleton.annual-production.backup.v1",
            "label": label, "sha256": digest,
            "bytes": size, "table_counts": counts,
        }
        raw = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
        mfd = os.open(seal, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(mfd, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        if os.name == "posix":
            dir_fd = os.open(folder, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        return verify_annual_snapshot(folder, label)
    finally:
        stage.unlink(missing_ok=True)


def restore_annual_snapshot(folder: Path, label: str, destination: Path) -> dict[str, Any]:
    """Copy a verified SQLite archive into a NEW independent, offline database.

    This never revives leases, starts Jeeves/Dragon/Builder workers, extends a
    grant, nor overwrites existing production. The destination is exposed only
    after full SQLite and chained-receipt validation of an independently
    copied image. An exclusive hard link publishes a COPY, never the source.
    """
    folder = _private_folder(Path(folder))
    verified = verify_annual_snapshot(folder, label)
    destination = Path(destination)
    if not destination.is_absolute() or destination.suffix != ".db":
        raise AnnualBackupError("restore requires a new absolute .db destination")
    parent = _private_folder(destination.parent)
    if any(p.exists() or p.is_symlink() for p in (
            destination, parent / (destination.name + "-wal"),
            parent / (destination.name + "-shm"),
            parent / (destination.name + "-journal"))):
        raise AnnualBackupError("restoration must not replace a live database or sidecar")
    fd, temporary = tempfile.mkstemp(prefix=".annual-restore-", suffix=".tmp", dir=parent)
    stage = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as output:
            with (folder / (label + ".db")).open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        digest, size = _sha_file(stage)
        if digest != verified["sha256"] or size != verified["bytes"]:
            raise AnnualBackupError("restored SQLite bytes differ from sealed archive")
        if _check_database(stage) != verified["table_counts"]:
            raise AnnualBackupError("restored SQLite journal chain differs from snapshot")
        # A historical lease or grant MUST NOT become usable just because a
        # file was restored. Preserve receipt chains but fence every worker
        # generation and expire each legacy authority. Only independent
        # operator-approved renew_authority() can resume nonterminal jobs.
        with sqlite3.connect(str(stage), timeout=5) as restored_db:
            restored_db.execute("PRAGMA journal_mode=DELETE")
            restored_db.execute(
                "UPDATE annual_productions SET "
                "authority_expires_at=0, lease_epoch=lease_epoch+1, "
                "lease_token_digest=NULL, lease_worker=NULL, "
                "lease_expires_at=NULL, "
                "status=CASE WHEN status='running' THEN 'waiting' ELSE status END"
            )
        if _check_database(stage) != verified["table_counts"]:
            raise AnnualBackupError("fenced restoration changed chain or table inventory")
        with sqlite3.connect(
            "file:" + quote(str(stage), safe="/") + "?mode=ro&immutable=1", uri=True,
        ) as restored_db:
            if restored_db.execute(
                "SELECT count(*) FROM annual_productions WHERE "
                "authority_expires_at!=0 OR lease_token_digest IS NOT NULL "
                "OR lease_worker IS NOT NULL OR lease_expires_at IS NOT NULL"
            ).fetchone()[0]:
                raise AnnualBackupError("historical worker/grant fencing failed")
        restored_digest, restored_size = _sha_file(stage)
        if verify_annual_snapshot(folder, label) != verified:
            raise AnnualBackupError("backup changed while restoring a new database")
        if any(p.exists() or p.is_symlink() for p in (
                destination, parent / (destination.name + "-wal"),
                parent / (destination.name + "-shm"),
                parent / (destination.name + "-journal"))):
            raise AnnualBackupError("live restore destination appeared during copy")
        try:
            os.link(stage, destination, follow_symlinks=False)
        except FileExistsError as exc:
            raise AnnualBackupError("restore destination appeared during publication") from exc
        if os.name == "posix":
            parent_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        return {
            **verified,
            "backup_restored": True,
            "independent_database_copy": True,
            "restored_database_sha256": restored_digest,
            "restored_database_bytes": restored_size,
            "historic_leases_and_grants_fenced": True,
            "workers_started": False,
            "old_worker_leases_validated_for_reuse": False,
            "new_operator_authorization_required": True,
        }
    finally:
        stage.unlink(missing_ok=True)
