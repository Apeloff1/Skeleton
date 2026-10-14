"""Versioned SQLite persistence for bounded model lifecycle candidates.

Storage does not grant production promotion or routing authority. The lifecycle
registry validates the complete evidence graph before using a stored snapshot.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from .lifecycle import ModelLifecycleError

APPLICATION_ID = 1296843609
SCHEMA_VERSION = 1
MAX_SNAPSHOT_BYTES = 16 * 1024 * 1024


class ModelLifecyclePersistenceError(ModelLifecycleError):
    """Durable candidate state is unavailable, conflicting or corrupt."""


def _canonical(value: object) -> str:
    try:
        result = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        if len(result.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
            raise ModelLifecyclePersistenceError("lifecycle snapshot exceeds bounded byte budget")
        return result
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ModelLifecyclePersistenceError("lifecycle snapshot is not bounded deterministic JSON") from exc


def _sha(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise ModelLifecyclePersistenceError("duplicate key in lifecycle snapshot")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ModelLifecyclePersistenceError("nonfinite number in lifecycle snapshot")


def _parse(payload: str) -> dict[str, object]:
    try:
        result = json.loads(payload, object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, TypeError, RecursionError) as exc:
        raise ModelLifecyclePersistenceError("invalid lifecycle snapshot JSON") from exc
    if not isinstance(result, dict) or _canonical(result) != payload:
        raise ModelLifecyclePersistenceError("lifecycle snapshot is not canonical object JSON")
    return result


def _path(value: str | Path) -> Path:
    if not isinstance(value, (str, Path)) or not str(value).strip() or str(value) == ":memory:":
        raise ModelLifecyclePersistenceError("durable lifecycle requires a nonempty filesystem path")
    return Path(value).expanduser().resolve()


@dataclass(frozen=True, slots=True)
class LifecycleBackupReceipt:
    path: str
    snapshot_version: int
    snapshot_digest: str
    schema_version: int = SCHEMA_VERSION


class LifecycleSnapshotTransaction:
    def __init__(
        self,
        connection: sqlite3.Connection,
        snapshot: dict[str, object] | None,
        version: int,
        snapshot_digest: str | None,
    ) -> None:
        self._connection = connection
        self.snapshot = snapshot
        self.version = version
        self.snapshot_digest = snapshot_digest

    def save(self, snapshot: Mapping[str, object]) -> None:
        payload = _canonical(snapshot)
        digest = _sha(payload)
        if digest == self.snapshot_digest:
            return
        if self.version >= (1 << 63) - 1:
            raise ModelLifecyclePersistenceError("lifecycle snapshot version exhausted")
        if self.version == 0:
            self._connection.execute(
                "INSERT INTO lifecycle_state(singleton,version,payload,digest) VALUES(1,1,?,?)",
                (payload, digest),
            )
        else:
            cursor = self._connection.execute(
                "UPDATE lifecycle_state SET version=?,payload=?,digest=? "
                "WHERE singleton=1 AND version=? AND digest=?",
                (self.version + 1, payload, digest, self.version, self.snapshot_digest),
            )
            if cursor.rowcount != 1:
                raise ModelLifecyclePersistenceError("lifecycle snapshot compare-and-set conflict")
        self.version += 1
        self.snapshot_digest = digest
        self.snapshot = _parse(payload)


class SQLiteModelLifecycleRepository:
    """One versioned candidate snapshot serialized across SQLite connections."""

    def __init__(
        self,
        path: str | Path,
        *,
        timeout_seconds: float = 5.0,
        initial_snapshot: Mapping[str, object] | None = None,
    ) -> None:
        self.path = _path(path)
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not 0 < timeout_seconds <= 60
        ):
            raise ModelLifecyclePersistenceError("timeout_seconds must be within (0, 60]")
        self.timeout_seconds = float(timeout_seconds)
        self._lock = RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                created = self._schema(connection, initialize=True)
                snapshot, version, digest = self._read(connection)
                if created:
                    empty = {
                        "schema_version": 1,
                        "budgets": {
                            "max_models": 128,
                            "max_transitions": 4096,
                            "max_decisions": 1024,
                            "max_parity_cases": 1024,
                        },
                        "mboms": [],
                        "states": {},
                        "history": [],
                        "decisions": [],
                        "migrations": [],
                        "rollbacks": [],
                    }
                    transaction = LifecycleSnapshotTransaction(connection, snapshot, version, digest)
                    transaction.save(empty if initial_snapshot is None else initial_snapshot)
                elif snapshot is None:
                    raise ModelLifecyclePersistenceError("durable lifecycle registry snapshot is missing")
                connection.commit()
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("PRAGMA synchronous=FULL")
            except sqlite3.Error as exc:
                connection.rollback()
                raise ModelLifecyclePersistenceError(
                    "cannot initialize lifecycle candidate repository"
                ) from exc

    @contextmanager
    def _connection(self, *, read_only: bool = False) -> Iterator[sqlite3.Connection]:
        connection = None
        try:
            if read_only:
                connection = sqlite3.connect(
                    self.path.as_uri() + "?mode=ro",
                    uri=True,
                    timeout=self.timeout_seconds,
                    isolation_level=None,
                )
            else:
                connection = sqlite3.connect(self.path, timeout=self.timeout_seconds, isolation_level=None)
                connection.execute("PRAGMA synchronous=FULL")
            connection.execute(f"PRAGMA busy_timeout={int(self.timeout_seconds * 1000)}")
            yield connection
        except sqlite3.Error as exc:
            raise ModelLifecyclePersistenceError("lifecycle candidate database operation failed") from exc
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _schema(connection: sqlite3.Connection, *, initialize: bool = False) -> bool:
        app_id = connection.execute("PRAGMA application_id").fetchone()[0]
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        objects = connection.execute(
            "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        ).fetchall()
        created = app_id == 0 and version == 0 and not objects and initialize
        if created:
            connection.execute(
                "CREATE TABLE lifecycle_state("
                "singleton INTEGER PRIMARY KEY CHECK(singleton=1),"
                "version INTEGER NOT NULL CHECK(version>0),payload TEXT NOT NULL,digest TEXT NOT NULL)"
            )
            connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
            connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        elif app_id != APPLICATION_ID or version != SCHEMA_VERSION:
            raise ModelLifecyclePersistenceError("unsupported or unrelated lifecycle database format")
        objects = connection.execute(
            "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        ).fetchall()
        columns = connection.execute("PRAGMA table_info(lifecycle_state)").fetchall()
        if objects != [("table", "lifecycle_state")] or [(row[1], row[2], row[5]) for row in columns] != [
            ("singleton", "INTEGER", 1),
            ("version", "INTEGER", 0),
            ("payload", "TEXT", 0),
            ("digest", "TEXT", 0),
        ]:
            raise ModelLifecyclePersistenceError("lifecycle database schema identity is corrupt")
        return created

    @staticmethod
    def _read(connection: sqlite3.Connection) -> tuple[dict[str, object] | None, int, str | None]:
        headers = connection.execute(
            "SELECT singleton,version,length(CAST(payload AS BLOB)),digest FROM lifecycle_state"
        ).fetchall()
        if not headers:
            return None, 0, None
        if len(headers) != 1:
            raise ModelLifecyclePersistenceError("lifecycle database has ambiguous snapshot identity")
        singleton, version, size, digest = headers[0]
        if singleton != 1 or not isinstance(version, int) or version <= 0:
            raise ModelLifecyclePersistenceError("invalid lifecycle snapshot sequence")
        if not isinstance(size, int) or not 1 <= size <= MAX_SNAPSHOT_BYTES:
            raise ModelLifecyclePersistenceError("lifecycle snapshot exceeds bounded byte budget")
        payload = connection.execute("SELECT payload FROM lifecycle_state WHERE singleton=1").fetchone()[0]
        if not isinstance(payload, str) or not isinstance(digest, str) or _sha(payload) != digest:
            raise ModelLifecyclePersistenceError("lifecycle snapshot digest mismatch")
        return _parse(payload), version, digest

    @contextmanager
    def transaction(self) -> Iterator[LifecycleSnapshotTransaction]:
        with self._lock, self._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._schema(connection)
                snapshot, version, digest = self._read(connection)
                if snapshot is None:
                    raise ModelLifecyclePersistenceError("durable lifecycle registry snapshot is missing")
                transaction = LifecycleSnapshotTransaction(connection, snapshot, version, digest)
                yield transaction
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def backup(
        self, destination: str | Path, *, validate: Callable[[dict[str, object]], object]
    ) -> LifecycleBackupReceipt:
        """Validate a pinned read snapshot and create a non-overwriting backup."""
        target = _path(destination)
        if target.exists() or target == self.path:
            raise ModelLifecyclePersistenceError("backup destination already exists")
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".lifecycle-backup-", suffix=".sqlite", dir=target.parent
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            with self._lock, self._connection(read_only=True) as source:
                source.execute("BEGIN")
                self._schema(source)
                snapshot, version, digest = self._read(source)
                if snapshot is None or digest is None:
                    raise ModelLifecyclePersistenceError("cannot back up an uninitialized lifecycle registry")
                validate(snapshot)
                with sqlite3.connect(temporary) as destination_connection:
                    source.backup(destination_connection)
                    destination_connection.execute("PRAGMA journal_mode=DELETE")
                    destination_connection.execute("PRAGMA synchronous=FULL")
                    copied, copied_version, copied_digest = self._read(destination_connection)
                    if copied_version != version or copied_digest != digest or copied is None:
                        raise ModelLifecyclePersistenceError("backup snapshot identity drift")
                    validate(copied)
                source.rollback()
            os.link(temporary, target)
            directory_fd = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return LifecycleBackupReceipt(str(target), version, digest)
        except (OSError, sqlite3.Error) as exc:
            raise ModelLifecyclePersistenceError(
                "lifecycle backup failed without replacing destination"
            ) from exc
        finally:
            temporary.unlink(missing_ok=True)

    @classmethod
    def restore(
        cls, backup: str | Path, destination: str | Path, *, validate: Callable[[dict[str, object]], object]
    ) -> tuple[SQLiteModelLifecycleRepository, LifecycleBackupReceipt]:
        """Restore a validated version-compatible backup into a new database."""
        source = _path(backup)
        if not source.is_file():
            raise ModelLifecyclePersistenceError("lifecycle backup does not exist")
        # Avoid initializing or modifying a backup before it has been validated.
        repository = object.__new__(cls)
        repository.path = source
        repository.timeout_seconds = 5.0
        repository._lock = RLock()
        receipt = repository.backup(destination, validate=validate)
        return cls(destination), receipt


__all__ = ["LifecycleBackupReceipt", "ModelLifecyclePersistenceError", "SQLiteModelLifecycleRepository"]
