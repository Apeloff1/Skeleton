"""Pack H versioned SQLite migrations with a small, idempotent runner.

Each migration is an ordered ``(version, name, statements)`` triple. The runner
records applied versions with a checksum of their SQL in ``pack_h_schema``; a
changed checksum for an already-applied version fails closed instead of
silently diverging. Applying is transactional per migration and safe to call
repeatedly and concurrently (``BEGIN IMMEDIATE`` serializes writers).
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple


class MigrationError(RuntimeError):
    pass


class MigrationDrift(MigrationError):
    """An applied migration's SQL no longer matches the code."""


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    statements: Tuple[str, ...]

    def __post_init__(self) -> None:
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise MigrationError("migration version must be a positive int")
        if not self.name or not self.name.replace("_", "").isalnum():
            raise MigrationError("migration name must be a non-empty identifier")
        if not self.statements:
            raise MigrationError("migration must contain at least one statement")

    @property
    def checksum(self) -> str:
        h = hashlib.sha256()
        for stmt in self.statements:
            h.update(" ".join(stmt.split()).encode("utf-8"))
            h.update(b"\x00")
        return h.hexdigest()


SCHEMA_TABLE = """
CREATE TABLE IF NOT EXISTS pack_h_schema (
    component  TEXT NOT NULL,
    version    INTEGER NOT NULL,
    name       TEXT NOT NULL,
    checksum   TEXT NOT NULL,
    applied_at REAL NOT NULL,
    PRIMARY KEY (component, version)
)
"""


def _validate_sequence(migrations: Sequence[Migration]) -> None:
    versions = [m.version for m in migrations]
    if versions != sorted(versions) or len(set(versions)) != len(versions):
        raise MigrationError("migrations must be strictly increasing by version")
    if versions and versions[0] != 1:
        raise MigrationError("migrations must start at version 1")
    for a, b in zip(versions, versions[1:]):
        if b != a + 1:
            raise MigrationError("migration versions must be contiguous")


def applied(conn: sqlite3.Connection, component: str) -> List[Tuple[int, str, str]]:
    conn.execute(SCHEMA_TABLE)
    rows = conn.execute(
        "SELECT version, name, checksum FROM pack_h_schema WHERE component = ? ORDER BY version",
        (component,),
    ).fetchall()
    return [(int(r[0]), str(r[1]), str(r[2])) for r in rows]


def current_version(conn: sqlite3.Connection, component: str) -> int:
    rows = applied(conn, component)
    return rows[-1][0] if rows else 0


def migrate(
    conn: sqlite3.Connection,
    component: str,
    migrations: Sequence[Migration],
    *,
    target: int | None = None,
) -> List[int]:
    """Apply pending migrations up to ``target`` (default: latest).

    Returns the versions applied by this call. Requires the connection to be in
    autocommit mode (``isolation_level=None``) so the runner owns transactions.
    """
    if not component or not component.replace("_", "").replace(".", "").isalnum():
        raise MigrationError("component must be an identifier")
    _validate_sequence(migrations)
    if conn.isolation_level is not None:
        raise MigrationError("connection must use isolation_level=None (autocommit)")
    goal = migrations[-1].version if target is None else int(target)
    if migrations and not 0 <= goal <= migrations[-1].version:
        raise MigrationError("target version out of range")
    conn.execute(SCHEMA_TABLE)
    done: List[int] = []
    for mig in migrations:
        if mig.version > goal:
            break
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT checksum FROM pack_h_schema WHERE component = ? AND version = ?",
                (component, mig.version),
            ).fetchone()
            if row is not None:
                if row[0] != mig.checksum:
                    raise MigrationDrift(
                        f"{component} migration {mig.version} ({mig.name}) checksum drift"
                    )
                conn.execute("COMMIT")
                continue
            for stmt in mig.statements:
                conn.execute(stmt)
            conn.execute(
                "INSERT INTO pack_h_schema (component, version, name, checksum, applied_at) VALUES (?, ?, ?, ?, ?)",
                (component, mig.version, mig.name, mig.checksum, time.time()),
            )
            conn.execute("COMMIT")
            done.append(mig.version)
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return done


def verify(conn: sqlite3.Connection, component: str, migrations: Iterable[Migration]) -> None:
    """Fail closed if any applied migration drifted or is unknown to the code."""
    known = {m.version: m for m in migrations}
    for version, name, checksum in applied(conn, component):
        mig = known.get(version)
        if mig is None:
            raise MigrationDrift(f"{component} has unknown applied migration {version} ({name})")
        if mig.checksum != checksum:
            raise MigrationDrift(f"{component} migration {version} ({name}) checksum drift")


def connect(path: str, *, timeout: float = 30.0) -> sqlite3.Connection:
    """Open an autocommit SQLite connection tuned for concurrent writers."""
    conn = sqlite3.connect(path, timeout=timeout, isolation_level=None, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    if path != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute(f"PRAGMA busy_timeout = {int(timeout * 1000)}")
    return conn


DURABLE_TIER_MIGRATIONS: Tuple[Migration, ...] = (
    Migration(1, "durable_tier_entries", (
        """CREATE TABLE IF NOT EXISTS pack_h_cache_entries (
            namespace  TEXT NOT NULL,
            key        TEXT NOT NULL,
            value      BLOB NOT NULL,
            codec      TEXT NOT NULL,
            version    INTEGER NOT NULL,
            expires_at REAL,
            updated_at REAL NOT NULL,
            PRIMARY KEY (namespace, key)
        )""",
        "CREATE INDEX IF NOT EXISTS pack_h_cache_expiry ON pack_h_cache_entries (expires_at)",
    )),
    Migration(2, "durable_tier_tombstones", (
        """CREATE TABLE IF NOT EXISTS pack_h_cache_tombstones (
            namespace  TEXT NOT NULL,
            key        TEXT NOT NULL,
            version    INTEGER NOT NULL,
            deleted_at REAL NOT NULL,
            PRIMARY KEY (namespace, key)
        )""",
    )),
)

IDEMPOTENCY_MIGRATIONS: Tuple[Migration, ...] = (
    Migration(1, "idempotency_records", (
        """CREATE TABLE IF NOT EXISTS pack_h_idempotency (
            scope        TEXT NOT NULL,
            key          TEXT NOT NULL,
            fingerprint  TEXT NOT NULL,
            state        TEXT NOT NULL CHECK (state IN ('in_flight', 'completed')),
            status_code  INTEGER,
            headers_json TEXT,
            body         BLOB,
            owner        TEXT NOT NULL,
            created_at   REAL NOT NULL,
            locked_until REAL NOT NULL,
            expires_at   REAL NOT NULL,
            PRIMARY KEY (scope, key)
        )""",
        "CREATE INDEX IF NOT EXISTS pack_h_idem_expiry ON pack_h_idempotency (expires_at)",
    )),
)

OUTBOX_MIGRATIONS: Tuple[Migration, ...] = (
    Migration(1, "outbox_events", (
        """CREATE TABLE IF NOT EXISTS pack_h_outbox (
            seq            INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id       TEXT NOT NULL UNIQUE,
            aggregate_type TEXT NOT NULL,
            aggregate_id   TEXT NOT NULL,
            event_type     TEXT NOT NULL,
            payload_json   TEXT NOT NULL,
            headers_json   TEXT NOT NULL,
            created_at     REAL NOT NULL,
            available_at   REAL NOT NULL,
            attempts       INTEGER NOT NULL DEFAULT 0,
            last_error     TEXT,
            claimed_by     TEXT,
            claimed_until  REAL,
            delivered_at   REAL,
            dead_at        REAL
        )""",
        """CREATE INDEX IF NOT EXISTS pack_h_outbox_ready
            ON pack_h_outbox (delivered_at, dead_at, available_at, seq)""",
        "CREATE INDEX IF NOT EXISTS pack_h_outbox_aggregate ON pack_h_outbox (aggregate_type, aggregate_id, seq)",
    )),
    Migration(2, "outbox_consumer_dedupe", (
        """CREATE TABLE IF NOT EXISTS pack_h_outbox_consumed (
            consumer    TEXT NOT NULL,
            event_id    TEXT NOT NULL,
            consumed_at REAL NOT NULL,
            PRIMARY KEY (consumer, event_id)
        )""",
    )),
)

RECORD_MIGRATIONS: Tuple[Migration, ...] = (
    Migration(1, "records", (
        """CREATE TABLE IF NOT EXISTS pack_h_records (
            tenant_id  TEXT NOT NULL,
            record_id  TEXT NOT NULL,
            kind       TEXT NOT NULL,
            body_json  TEXT NOT NULL,
            version    INTEGER NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            deleted_at REAL,
            PRIMARY KEY (tenant_id, record_id)
        )""",
        "CREATE INDEX IF NOT EXISTS pack_h_records_kind ON pack_h_records (tenant_id, kind, updated_at)",
    )),
)

ALL_COMPONENTS = {
    "durable_tier": DURABLE_TIER_MIGRATIONS,
    "idempotency": IDEMPOTENCY_MIGRATIONS,
    "outbox": OUTBOX_MIGRATIONS,
    "records": RECORD_MIGRATIONS,
}


def migrate_all(conn: sqlite3.Connection) -> dict[str, List[int]]:
    return {name: migrate(conn, name, migs) for name, migs in ALL_COMPONENTS.items()}
