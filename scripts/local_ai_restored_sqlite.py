#!/usr/bin/env python3
"""Independent read-only SQLite integrity audit of verified offline restores.

Only already-rehydrated NEW private directories are inspected, and only AFTER
source receipt SHA, every archived byte, and every restored byte passes the
existing independent custody check. Never connect to a live Docker volume.

SQLite structural integrity is separate from Mongo WiredTiger consistency,
Chroma vector/index consistency and cross-store transaction atomicity. An
integrity-clean SQLite database does NOT prove application restore readiness.
WAL/SHM/journal sidecars are explicitly denied, not silently ignored by
SQLite's immutable snapshot option.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
from urllib.parse import quote

from scripts import local_ai_data_rehydration as rehydrate
from scripts import local_ai_volume_copy as worker
from scripts import local_ai_docker as host

SCHEMA = "skeleton.local-ai.docker.restored-sqlite-integrity.v1"
_ROLES = frozenset(("backend_data", "skeleton_data", "chroma_data"))
_SUFFIXES = (".sqlite", ".sqlite3", ".db")
_JOURNAL_SUFFIXES = ("-wal", "-shm", "-journal")
_MAX_SQLITE = 32
_MAX_SQLITE_BYTES = 2 * 1024**3
_MAX_SECONDS = 60
_PROGRESS_STEPS = 4096


class RestoredSQLiteError(host.LocalDockerError):
    """Restored SQLite integrity cannot safely be qualified."""


def _is_database(name: str) -> bool:
    return name.lower().endswith(_SUFFIXES)


def _is_sidecar(name: str) -> bool:
    lower = name.lower()
    for suffix in _JOURNAL_SUFFIXES:
        if lower.endswith(suffix) and _is_database(lower[:-len(suffix)]):
            return True
    return False


def _state(path: Path) -> tuple[int, int, int, int, int]:
    try:
        meta = path.lstat()
        if (not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1
                or meta.st_mode & 0o077
                or not 0 < meta.st_size <= _MAX_SQLITE_BYTES):
            raise RestoredSQLiteError("restored SQLite file is not private and bounded")
        return (
            meta.st_dev, meta.st_ino, meta.st_size,
            meta.st_mtime_ns, meta.st_ctime_ns,
        )
    except OSError:
        raise RestoredSQLiteError("restored SQLite metadata unavailable") from None


def _integrity(path: Path, *, deadline: float) -> tuple[str, int]:
    """Run SQLite's full integrity check read-only without creating journals."""
    original = _state(path)
    try:
        before_sha, before_size = worker._digest_file(path, expected_size=original[2])
        if before_size != original[2]:
            raise RestoredSQLiteError("restored SQLite custody changed before audit")
        # Quoted absolute paths are supplied as URI path bytes (not SQL).
        # immutable=1 explicitly ignores sidecars; the caller refuses ALL
        # WAL/SHM/journal candidates before entering this function.
        uri = "file:" + quote(str(path), safe="/") + "?mode=ro&immutable=1"
        with sqlite3.connect(uri, uri=True, timeout=0.0) as connection:
            connection.enable_load_extension(False)
            connection.execute("PRAGMA query_only=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.set_progress_handler(
                lambda: 1 if time.monotonic() > deadline else 0,
                _PROGRESS_STEPS,
            )
            if time.monotonic() > deadline:
                raise RestoredSQLiteError("restored SQLite audit deadline exceeded")
            rows = connection.execute("PRAGMA integrity_check")
            first = rows.fetchone()
            if (first != ("ok",) or rows.fetchone() is not None
                    or time.monotonic() > deadline):
                raise RestoredSQLiteError("restored SQLite structural integrity failed")
            # Foreign-key violations cannot be smuggled behind clean pages.
            if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise RestoredSQLiteError("restored SQLite foreign keys inconsistent")
        after_sha, after_size = worker._digest_file(path, expected_size=original[2])
        if ((after_sha, after_size) != (before_sha, before_size)
                or _state(path) != original):
            raise RestoredSQLiteError("restored SQLite bytes changed during audit")
        return before_sha, before_size
    except RestoredSQLiteError:
        raise
    except (sqlite3.Error, OSError, ValueError, TypeError):
        # SQLite errors could contain private paths or schema/record strings.
        raise RestoredSQLiteError("restored SQLite integrity unavailable") from None


def verify_restored_sqlite(
    source: Path, destination: Path, *,
    expected_receipt_sha256: str,
    max_databases: int = _MAX_SQLITE,
) -> dict[str, object]:
    """No-write logical SQLite-only subgate on independently verified bytes."""
    if (type(max_databases) is not int
            or not 1 <= max_databases <= _MAX_SQLITE):
        raise RestoredSQLiteError("SQLite database count limit invalid")
    try:
        verified = rehydrate.verify_rehydration(
            source, destination,
            expected_receipt_sha256=expected_receipt_sha256,
        )
    except Exception:
        raise RestoredSQLiteError("offline byte rehydration not independently verified") from None
    if (verified.get("database_process_started") is not False
            or verified.get("docker_daemon_used") is not False
            or verified.get("cross_store_snapshot_atomic") is not False
            or verified.get("application_restore_qualified") is not False
            or verified.get("sqlite_consistency_verified") is not False):
        raise RestoredSQLiteError("recovery prerequisite escalated database authority")
    roles = verified.get("roles")
    if (not isinstance(roles, list)
            or set(roles) not in (
                {"mongo_data", "mongo_config", "backend_data", "skeleton_data"},
                {"mongo_data", "mongo_config", "backend_data",
                 "skeleton_data", "chroma_data"},
            )):
        raise RestoredSQLiteError("restored application role inventory invalid")
    target = rehydrate.cold._private_root(destination, must_exist=True)
    if not target.is_dir() or target.is_symlink():
        raise RestoredSQLiteError("restored application root is not private")
    checked = 0
    total = 0
    digest = hashlib.sha256(b"skeleton.restored-sqlite-integrity.v1\x00")
    deadline = time.monotonic() + _MAX_SECONDS
    # Pass 1: reject *any* recognized journal sidecars before touching any
    # database, and count candidate SQLite names within a hard resource cap.
    for role in sorted(set(roles) & _ROLES):
        try:
            paths = worker._walk(target / role)
            for relative in paths:
                if time.monotonic() > deadline:
                    raise RestoredSQLiteError("restored SQLite inventory deadline exceeded")
                name = relative.as_posix()
                if _is_sidecar(name):
                    raise RestoredSQLiteError("restored SQLite uncheckpointed sidecar present")
                if _is_database(name):
                    checked += 1
                    if checked > max_databases:
                        raise RestoredSQLiteError("restored SQLite inventory count exceeded")
        except RestoredSQLiteError:
            raise
        except Exception:
            raise RestoredSQLiteError("restored SQLite inventory untrusted") from None
    if checked == 0:
        return {
            "schema": SCHEMA,
            "status": "no_restored_sqlite_candidates_not_database_qualified",
            "sqlite_databases_detected": 0,
            "sqlite_databases_integrity_checked": 0,
            "sqlite_total_bytes": 0,
            "all_detected_sqlite_integrity_ok": False,
            "sqlite_wal_or_journal_accepted": False,
            "source_archive_modified": False,
            "restored_bytes_modified": False,
            "docker_daemon_used": False,
            "mongo_consistency_verified": False,
            "chroma_consistency_verified": False,
            "cross_store_snapshot_atomic": False,
            "application_restore_qualified": False,
            "protected_jeeves_chat_qualified": False,
            "release_authorized": False,
        }
    for role in sorted(set(roles) & _ROLES):
        try:
            for relative in worker._walk(target / role):
                if not _is_database(relative.as_posix()):
                    continue
                if time.monotonic() > deadline:
                    raise RestoredSQLiteError("restored SQLite integrity deadline exceeded")
                sha, size = _integrity(target / role / relative, deadline=deadline)
                # The digest does not contain paths, schema or source records.
                # Domain-separated role and size are metadata only.
                digest.update(role.encode("ascii") + b"\0")
                digest.update(str(size).encode("ascii") + b"\0")
                digest.update(bytes.fromhex(sha))
                total += size
        except RestoredSQLiteError:
            raise
        except Exception:
            raise RestoredSQLiteError("restored SQLite verification unavailable") from None
    return {
        "schema": SCHEMA,
        "status": "restored_sqlite_integrity_only_not_application_recovery",
        "sqlite_databases_detected": checked,
        "sqlite_databases_integrity_checked": checked,
        "sqlite_total_bytes": total,
        "aggregate_content_fingerprint_sha256": digest.hexdigest(),
        "all_detected_sqlite_integrity_ok": True,
        "sqlite_wal_or_journal_accepted": False,
        "source_archive_modified": False,
        "restored_bytes_modified": False,
        "docker_daemon_used": False,
        "mongo_consistency_verified": False,
        "chroma_consistency_verified": False,
        "cross_store_snapshot_atomic": False,
        "application_restore_qualified": False,
        "protected_jeeves_chat_qualified": False,
        "release_authorized": False,
    }


__all__ = [
    "RestoredSQLiteError", "verify_restored_sqlite",
]
