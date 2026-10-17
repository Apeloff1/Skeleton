"""SQLite database + forward-only versioned migrations for app services."""
from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

MIGRATIONS: tuple[tuple[int, str, str], ...] = (
    (1, "users_and_sessions", """
        CREATE TABLE users (
            user_id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            display_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            disabled INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE TABLE sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            token_digest TEXT NOT NULL UNIQUE,
            scopes TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX idx_sessions_user ON sessions(user_id);
    """),
    (2, "projects_and_builds", """
        CREATE TABLE projects (
            project_id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL REFERENCES users(user_id),
            name TEXT NOT NULL,
            settings TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            UNIQUE(owner_id, name)
        );
        CREATE TABLE builds (
            build_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
            status TEXT NOT NULL,
            target TEXT NOT NULL DEFAULT '',
            job_id TEXT,
            result TEXT NOT NULL DEFAULT '{}',
            error TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE INDEX idx_builds_project ON builds(project_id, created_at);
    """),
    (3, "job_queue", """
        CREATE TABLE jobs (
            job_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            status TEXT NOT NULL,
            payload TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL,
            run_after REAL NOT NULL,
            lease_owner TEXT NOT NULL DEFAULT '',
            lease_expires_at REAL NOT NULL DEFAULT 0,
            correlation_id TEXT NOT NULL DEFAULT '',
            idempotency_key TEXT UNIQUE,
            progress REAL NOT NULL DEFAULT 0,
            result TEXT NOT NULL DEFAULT '{}',
            error TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE INDEX idx_jobs_ready ON jobs(status, run_after);
    """),
    (4, "assets", """
        CREATE TABLE assets (
            asset_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            size INTEGER NOT NULL,
            content_type TEXT NOT NULL,
            created_at REAL NOT NULL,
            UNIQUE(project_id, name)
        );
        CREATE INDEX idx_assets_sha ON assets(sha256);
    """),
)


class Database:
    """Thread-safe SQLite handle (WAL, FK on).  ``:memory:`` supported."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False,
                                     isolation_level=None, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        if self.path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.RLock()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            self._conn.execute("COMMIT")

    def query(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, args))

    def schema_version(self) -> int:
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at REAL NOT NULL)")
            row = self._conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
            return int(row[0] or 0)

    def migrate(self, target: int | None = None) -> list[int]:
        """Apply pending migrations in order; returns versions applied."""
        applied: list[int] = []
        current = self.schema_version()
        for version, name, sql in MIGRATIONS:
            if version <= current or (target is not None and version > target):
                continue
            with self.tx() as conn:
                for stmt in filter(None, (s.strip() for s in sql.split(";"))):
                    conn.execute(stmt)
                conn.execute("INSERT INTO schema_migrations VALUES (?,?,?)",
                             (version, name, time.time()))
            applied.append(version)
        return applied

    def close(self) -> None:
        with self._lock:
            self._conn.close()
