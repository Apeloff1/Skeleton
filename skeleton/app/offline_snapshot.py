"""Portable, verified, no-cloud recovery for local AI SQLite data.

Snapshots use SQLite's online backup API rather than byte-copying live WAL
databases. Each supported database remains its own application-shell state
domain: these backups never become production conversation or inference
authority. SHA-256 detects damage, not malicious modification or authenticity.
"""
from __future__ import annotations

import hashlib
import json
from contextlib import closing
import math
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
from typing import Any, Mapping

from .offline_sqlite_safety import check_sqlite_companion_paths, UnsafeOfflineSqlitePath


SCHEMA = "skeleton.app.offline_snapshot.v1"
KINDS = {
    "workspace": ("workspace.sqlite", "offline_conversations"),
    "library": ("library.sqlite", "offline_documents"),
    "queue": ("queue.sqlite", "offline_index_jobs"),
}
MAX_DATABASE_BYTES = 512 * 1024 * 1024
MAX_MANIFEST_BYTES = 16 * 1024


class OfflineSnapshotError(RuntimeError):
    """The requested offline data recovery cannot be safely admitted."""


def _source(path: str | Path) -> Path:
    source = Path(os.path.abspath(Path(path).expanduser()))
    if source.is_symlink() or not source.is_file():
        raise OfflineSnapshotError("snapshot input must be a regular local SQLite database")
    try:
        check_sqlite_companion_paths(source)
    except UnsafeOfflineSqlitePath as exc:
        raise OfflineSnapshotError(str(exc)) from exc
    if source.stat().st_size > MAX_DATABASE_BYTES:
        raise OfflineSnapshotError("offline SQLite database exceeds portable snapshot limit")
    return source


def _destination(path: str | Path) -> Path:
    target = Path(path).expanduser().absolute()
    if not target.parent.is_dir() or target.exists() or target.is_symlink():
        raise OfflineSnapshotError("snapshot destination must not exist and needs a valid parent")
    return target


def _digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as reader:
        for chunk in iter(lambda: reader.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _verify_database(path: Path, kind: str) -> None:
    path = _source(path)
    if kind not in KINDS:
        raise OfflineSnapshotError("unsupported offline SQLite data domain")
    # URI mode=ro prevents a validation probe from creating a missing DB.
    # Explicit absolute local paths are supplied by the operator.
    try:
        conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=10.0)
        try:
            check = conn.execute("PRAGMA integrity_check").fetchone()
            if check != ("ok",):
                raise OfflineSnapshotError("SQLite integrity check failed")
            table = KINDS[kind][1]
            found = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if found is None:
                raise OfflineSnapshotError("SQLite schema does not match snapshot domain")
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise OfflineSnapshotError("cannot verify offline SQLite database") from exc
    # SQLite integrity alone cannot detect forged, internally inconsistent
    # app data. Semantic inspection also checks transcript checksum/order,
    # FTS row mappings and valid durable queue receipts.
    from .offline_audit import OfflineAuditError, audit_database
    try:
        audit_database(path, kind)
    except OfflineAuditError as exc:
        raise OfflineSnapshotError(
            "offline SQLite semantic integrity check failed: " + str(exc)
        ) from exc


def _online_backup(source: Path, destination: Path, kind: str) -> None:
    source = _source(source)
    _verify_database(source, kind)
    # sqlite backup creates a consistent image even with source WAL pages.
    try:
        source_db = sqlite3.connect(
            source.as_uri() + "?mode=ro", uri=True, timeout=15.0,
        )
        try:
            target_db = sqlite3.connect(str(destination), timeout=15.0)
            try:
                source_db.backup(target_db, pages=128, sleep=0.1)
            finally:
                target_db.close()
        finally:
            source_db.close()
        # A WAL-mode source can propagate its journal setting through the
        # online backup. Normalize the isolated snapshot to a single-file
        # rollback-journal DB before digesting/publishing. This also avoids
        # dangling -wal/-shm files in the portable snapshot directory.
        with closing(sqlite3.connect(str(destination), timeout=15.0)) as compact:
            mode = compact.execute("PRAGMA journal_mode=DELETE").fetchone()
            if mode is None or mode[0].lower() != "delete":
                raise OfflineSnapshotError("cannot normalize snapshot journal mode")
        if os.name == "posix":
            os.chmod(destination, 0o600)
        _verify_database(destination, kind)
    except (sqlite3.Error, OSError) as exc:
        raise OfflineSnapshotError("SQLite online backup failed") from exc


def _publish_new_snapshot(stage: Path, target: Path) -> None:
    """Expose a verified snapshot without replacing a competing directory.

    mkdir and hardlinks fail if the destination already exists. The
    manifest is published *last*: readers may see an incomplete directory
    during publication, but verify_snapshot must reject it without the
    final manifest. No existing user path is removed or replaced.
    """
    os.mkdir(target, 0o700)
    written: list[str] = []
    try:
        for path in sorted(stage.iterdir(), key=lambda item: item.name):
            if path.name == "manifest.json":
                continue
            os.link(path, target / path.name)
            written.append(path.name)
        os.link(stage / "manifest.json", target / "manifest.json")
        written.append("manifest.json")
    except BaseException:
        for name in reversed(written):
            existing = target / name
            try:
                if existing.is_file() and os.path.samefile(existing, stage / name):
                    existing.unlink()
            except OSError:
                pass
        try:
            target.rmdir()
        except OSError:
            pass
        raise


def create_snapshot(
    destination: str | Path,
    *,
    workspace: str | Path | None = None,
    library: str | Path | None = None,
    queue: str | Path | None = None,
) -> dict[str, Any]:
    """Publish a verified local backup without clobbering another user path."""
    sources = {
        name: _source(path)
        for name, path in {
            "workspace": workspace, "library": library, "queue": queue,
        }.items()
        if path is not None
    }
    if not sources:
        raise OfflineSnapshotError("select at least one offline database to back up")
    target = _destination(destination)
    if any(target == source or target in source.parents for source in sources.values()):
        raise OfflineSnapshotError("snapshot must be outside all input database paths")
    with tempfile.TemporaryDirectory(
        prefix=".skeleton-local-recovery-", dir=target.parent,
    ) as temporary:
        stage = Path(temporary) / "snapshot"
        stage.mkdir(mode=0o700)
        files: dict[str, dict[str, int | str]] = {}
        for name, path in sorted(sources.items()):
            filename = KINDS[name][0]
            dest = stage / filename
            _online_backup(path, dest, name)
            size = dest.stat().st_size
            if size > MAX_DATABASE_BYTES:
                raise OfflineSnapshotError("backed up SQLite file exceeds quota")
            files[name] = {"filename": filename, "size_bytes": size, "sha256": _digest(dest)}
        manifest: dict[str, Any] = {
            "schema_version": SCHEMA,
            "created_at": time.time(),
            "databases": files,
            "consistent_across_databases": False,
            "signed": False,
        }
        encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(encoded) > MAX_MANIFEST_BYTES:
            raise OfflineSnapshotError("snapshot manifest size exceeds limit")
        (stage / "manifest.json").write_bytes(encoded + b"\n")
        verify_snapshot(stage)
        _publish_new_snapshot(stage, target)
    return manifest


def _strict_object(items: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in items:
        if key in output:
            raise OfflineSnapshotError("duplicate snapshot manifest JSON key")
        output[key] = value
    return output


def verify_snapshot(folder: str | Path) -> dict[str, Any]:
    base = Path(folder).expanduser()
    if base.is_symlink() or not base.is_dir():
        raise OfflineSnapshotError("snapshot must be a regular local directory")
    manifest_file = base / "manifest.json"
    if manifest_file.is_symlink() or not manifest_file.is_file():
        raise OfflineSnapshotError("snapshot manifest is missing or symlinked")
    if manifest_file.stat().st_size > MAX_MANIFEST_BYTES:
        raise OfflineSnapshotError("snapshot manifest exceeds limit")
    try:
        data = json.loads(
            manifest_file.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
        )
    except (ValueError, UnicodeError, OSError) as exc:
        raise OfflineSnapshotError("snapshot manifest is not valid JSON") from exc
    if (
        not isinstance(data, dict)
        or set(data) != {"schema_version", "created_at", "databases",
                            "consistent_across_databases", "signed"}
        or data["schema_version"] != SCHEMA
        or data["consistent_across_databases"] is not False
        or data["signed"] is not False
        or not isinstance(data["databases"], dict)
        or not 1 <= len(data["databases"]) <= len(KINDS)
        or not set(data["databases"]).issubset(KINDS)
        or type(data["created_at"]) not in (int, float)
        or not math.isfinite(data["created_at"])
    ):
        raise OfflineSnapshotError("offline snapshot schema mismatch")
    listed = {"manifest.json"}
    for kind, entry in data["databases"].items():
        expected_filename = KINDS[kind][0]
        if (
            not isinstance(entry, dict)
            or set(entry) != {"filename", "size_bytes", "sha256"}
            or entry["filename"] != expected_filename
            or type(entry["size_bytes"]) is not int
            or not 0 < entry["size_bytes"] <= MAX_DATABASE_BYTES
            or not isinstance(entry["sha256"], str)
            or len(entry["sha256"]) != 64
            or any(c not in "0123456789abcdef" for c in entry["sha256"])
        ):
            raise OfflineSnapshotError("offline snapshot database manifest invalid")
        file = base / expected_filename
        _source(file)
        if file.stat().st_size != entry["size_bytes"] or _digest(file) != entry["sha256"]:
            raise OfflineSnapshotError("offline snapshot database checksum mismatch")
        _verify_database(file, kind)
        listed.add(expected_filename)
    # Refuse undeclared payloads, directory traversal and symlink drop-ins.
    if {item.name for item in base.iterdir()} != listed:
        raise OfflineSnapshotError("offline snapshot contains unexpected files")
    return data


def _quarantine_restored_queue(path: Path) -> None:
    """Never replay source paths or lease authority from another installation.

    A restored queue can contain active jobs with source/library paths that
    belong to the *old* device or installation. Preserve completed audit
    history while neutralizing every actionable pre-restore job. Operators
    must explicitly enqueue fresh work against the new local paths.
    """
    try:
        with closing(sqlite3.connect(str(path), isolation_level=None, timeout=10)) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "UPDATE offline_index_jobs SET "
                    "state='cancelled', lease_token=NULL, lease_until=NULL, "
                    "result_json=NULL, "
                    "last_error='restored queue: explicitly enqueue work for this device' "
                    "WHERE state IN ('queued', 'running', 'failed')"
                )
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
    except sqlite3.Error as exc:
        raise OfflineSnapshotError("cannot quarantine restored indexing jobs") from exc


def restore_snapshot(
    folder: str | Path,
    *,
    workspace: str | Path | None = None,
    library: str | Path | None = None,
    queue: str | Path | None = None,
) -> dict[str, Any]:
    """Restore all selected databases, never overwriting an existing target.

    Each SQLite database is independently consistent. This does not claim a
    global atomic snapshot across the conversation, library and queue planes.
    """
    source = Path(folder).expanduser()
    manifest = verify_snapshot(source)
    targets = {
        kind: _destination(path)
        for kind, path in {
            "workspace": workspace, "library": library, "queue": queue,
        }.items()
        if path is not None
    }
    if set(targets) != set(manifest["databases"]):
        raise OfflineSnapshotError("restore destinations must match every snapshot domain")
    if len(set(targets.values())) != len(targets):
        raise OfflineSnapshotError("restore database paths must be distinct")
    staged: list[tuple[Path, Path, str]] = []
    published: list[tuple[Path, Path]] = []
    try:
        for kind, target in sorted(targets.items()):
            with tempfile.NamedTemporaryFile(
                dir=target.parent, prefix=".skeleton-db-recover-",
                suffix=".sqlite", delete=False,
            ) as tmp:
                temporary = Path(tmp.name)
            staged.append((temporary, target, kind))
            if os.name == "posix":
                os.chmod(temporary, 0o600)
            shutil.copyfile(source / KINDS[kind][0], temporary)
            if _digest(temporary) != manifest["databases"][kind]["sha256"]:
                raise OfflineSnapshotError("restore copy differs from verified input")
            _verify_database(temporary, kind)
            if kind == "queue":
                # The manifest verifies input integrity; the restored copy
                # intentionally has different bytes because old leases and
                # path-based pending authority cannot be safely replayed.
                _quarantine_restored_queue(temporary)
                _verify_database(temporary, kind)
        # Publish only after *every* domain has passed its own validation.
        # If a later publish fails, delete only files made in this operation.
        for temporary, target, _kind in staged:
            _destination(target)
            # Hard-link creation fails if target already exists, unlike
            # os.replace which could silently overwrite a user database.
            os.link(temporary, target)
            published.append((target, temporary))
    except BaseException:
        for produced, source_copy in published:
            try:
                # Only roll back the inode *we* linked. If another process
                # replaced the destination path, never delete its file.
                if os.path.samefile(produced, source_copy):
                    produced.unlink()
            except OSError:
                pass
        raise
    finally:
        for temporary, _target, _kind in staged:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
    return manifest


__all__ = [
    "SCHEMA", "OfflineSnapshotError", "create_snapshot",
    "verify_snapshot", "restore_snapshot",
]
