"""Bounded, restart-safe, device-local document indexing queue.

This application-shell queue is not an autonomous AI control plane. It
executes only an explicitly enqueued local directory scan through the
canonical offline document library, never arbitrary commands or URLs.
Jobs are leased, revisioned and fenced so a restarted worker cannot
overwrite a later worker's completion record.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
from typing import Any

from .offline_library import OfflineDocumentLibrary, _root


SCHEMA = "skeleton.app.offline_index_queue.v1"
MAX_ATTEMPTS = 3
LEASE_SECONDS = 900
MAX_RUN_BATCH = 20
MAX_STORED_JOBS = 5000


class OfflineQueueError(RuntimeError):
    """Invalid queue operation or corrupt local job state."""


@dataclass(frozen=True)
class IndexJob:
    job_id: str
    state: str
    source: str
    library: str
    attempts: int
    created_at: float
    updated_at: float
    next_due_at: float
    last_error: str | None
    result: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "state": self.state,
            "source": self.source,
            "library": self.library,
            "attempts": self.attempts,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "next_due_at": self.next_due_at,
            "last_error": self.last_error,
            "result": self.result,
        }


def _job_id(value: str) -> str:
    if not isinstance(value, str) or len(value) != 32:
        raise OfflineQueueError("job id must be a 32-character hex token")
    try:
        bytes.fromhex(value)
    except ValueError as exc:
        raise OfflineQueueError("invalid hex job id") from exc
    return value


def _local_db(path: str | Path) -> Path:
    p = Path(path).expanduser()
    if not p.parent.is_dir() or p.is_symlink() or (
        p.exists() and not p.is_file()
    ):
        raise OfflineQueueError("queue or index must be a regular local SQLite path")
    return Path(os.path.abspath(p))


def _as_job(row: tuple[Any, ...]) -> IndexJob:
    job_id, state, source, library, attempts, created, updated, due, error, result = row
    if state not in ("queued", "running", "completed", "failed", "cancelled"):
        raise OfflineQueueError("invalid stored job lifecycle state")
    if type(attempts) is not int or not 0 <= attempts <= MAX_ATTEMPTS:
        raise OfflineQueueError("invalid stored job attempt count")
    try:
        summary = json.loads(result) if result is not None else None
    except (ValueError, TypeError) as exc:
        raise OfflineQueueError("corrupt local index job result") from exc
    if summary is not None and not isinstance(summary, dict):
        raise OfflineQueueError("invalid local index result envelope")
    return IndexJob(
        job_id, state, source, library, attempts,
        created, updated, due, error, summary,
    )


_COLUMNS = (
    "job_id, state, source, library, attempts, created_at, updated_at, "
    "next_due_at, last_error, result_json"
)


class OfflineIndexQueue:
    """SQLite-backed explicit user jobs with atomic lease claiming."""

    def __init__(self, path: str | Path) -> None:
        self.path = _local_db(path)
        self._lock = threading.RLock()
        was_present = self.path.exists()
        try:
            self._db = sqlite3.connect(
                str(self.path), timeout=10.0, isolation_level=None,
                check_same_thread=False,
            )
            if not was_present and os.name == "posix":
                os.chmod(self.path, 0o600)
            self._db.execute("PRAGMA busy_timeout=10000")
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.execute("""CREATE TABLE IF NOT EXISTS offline_index_jobs (
                job_id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                source TEXT NOT NULL,
                library TEXT NOT NULL,
                attempts INTEGER NOT NULL CHECK(attempts >= 0 AND attempts <= 3),
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                next_due_at REAL NOT NULL,
                lease_token TEXT,
                lease_until REAL,
                last_error TEXT,
                result_json TEXT
            )""")
            self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_index_jobs_due "
                "ON offline_index_jobs(state, next_due_at, created_at)"
            )
        except sqlite3.Error as exc:
            raise OfflineQueueError("cannot open local indexing job queue") from exc

    def __enter__(self) -> "OfflineIndexQueue":
        return self

    def __exit__(self, *_unused: object) -> None:
        self.close()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def enqueue(self, directory: str | Path, library: str | Path) -> IndexJob:
        source = str(_root(directory))
        target = str(_local_db(library))
        if target == str(self.path):
            raise OfflineQueueError("queue database and document library must differ")
        now = time.time()
        with self._lock:
            # BEGIN IMMEDIATE makes deduplication atomic across *processes*.
            self._db.execute("BEGIN IMMEDIATE")
            try:
                row = self._db.execute(
                    f"SELECT {_COLUMNS} FROM offline_index_jobs "
                    "WHERE source=? AND library=? AND state IN ('queued','running') "
                    "ORDER BY created_at LIMIT 1", (source, target),
                ).fetchone()
                if row is not None:
                    self._db.execute("COMMIT")
                    return _as_job(row)
                total = self._db.execute(
                    "SELECT COUNT(*) FROM offline_index_jobs"
                ).fetchone()[0]
                if total >= MAX_STORED_JOBS:
                    raise OfflineQueueError(
                        "local indexing queue storage quota is exhausted"
                    )
                job_id = secrets.token_hex(16)
                self._db.execute(
                    "INSERT INTO offline_index_jobs "
                    "(job_id,state,source,library,attempts,created_at,updated_at,"
                    "next_due_at) VALUES (?,'queued',?,?,0,?,?,?)",
                    (job_id, source, target, now, now, now),
                )
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        return self.get(job_id)

    def get(self, job_id: str) -> IndexJob:
        job_id = _job_id(job_id)
        with self._lock:
            try:
                row = self._db.execute(
                    f"SELECT {_COLUMNS} FROM offline_index_jobs WHERE job_id=?",
                    (job_id,),
                ).fetchone()
            except sqlite3.Error as exc:
                raise OfflineQueueError("cannot load offline job") from exc
        if row is None:
            raise OfflineQueueError("unknown local indexing job")
        return _as_job(row)

    def list_jobs(self, *, limit: int = 100) -> tuple[IndexJob, ...]:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise OfflineQueueError("invalid indexing job list bound")
        with self._lock:
            try:
                rows = self._db.execute(
                    f"SELECT {_COLUMNS} FROM offline_index_jobs "
                    "ORDER BY created_at DESC, job_id LIMIT ?", (limit,),
                ).fetchall()
            except sqlite3.Error as exc:
                raise OfflineQueueError("cannot list local indexing jobs") from exc
        return tuple(_as_job(row) for row in rows)

    def cancel(self, job_id: str) -> IndexJob:
        job_id = _job_id(job_id)
        now = time.time()
        with self._lock:
            cursor = self._db.execute(
                "UPDATE offline_index_jobs "
                "SET state='cancelled', updated_at=?, lease_token=NULL, lease_until=NULL "
                "WHERE job_id=? AND state='queued'", (now, job_id),
            )
        if cursor.rowcount != 1:
            raise OfflineQueueError("only queued jobs can be cancelled")
        return self.get(job_id)

    def retry(self, job_id: str) -> IndexJob:
        job_id = _job_id(job_id)
        now = time.time()
        with self._lock:
            cursor = self._db.execute(
                "UPDATE offline_index_jobs "
                "SET state='queued', attempts=0, updated_at=?, next_due_at=?, "
                "last_error=NULL, lease_token=NULL, lease_until=NULL "
                "WHERE job_id=? AND state='failed'", (now, now, job_id),
            )
        if cursor.rowcount != 1:
            raise OfflineQueueError("only terminal failed jobs may be retried")
        return self.get(job_id)

    def _claim(self) -> tuple[IndexJob, str] | None:
        now = time.time()
        token = secrets.token_hex(16)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                # An abandoned worker at its attempt budget is terminal.
                # Never increment attempts past the table's CHECK bound.
                self._db.execute(
                    "UPDATE offline_index_jobs SET state='failed', updated_at=?, "
                    "last_error='expired worker lease after maximum attempts', "
                    "lease_token=NULL, lease_until=NULL "
                    "WHERE state='running' AND lease_until<=? AND attempts>=?",
                    (now, now, MAX_ATTEMPTS),
                )
                row = self._db.execute(
                    f"SELECT {_COLUMNS} FROM offline_index_jobs "
                    "WHERE (state='queued' AND next_due_at<=?) "
                    "OR (state='running' AND lease_until<=? AND attempts<?) "
                    "ORDER BY created_at, job_id LIMIT 1",
                    (now, now, MAX_ATTEMPTS),
                ).fetchone()
                if row is None:
                    self._db.execute("COMMIT")
                    return None
                job = _as_job(row)
                self._db.execute(
                    "UPDATE offline_index_jobs SET state='running', attempts=attempts+1, "
                    "updated_at=?, lease_token=?, lease_until=? WHERE job_id=?",
                    (now, token, now + LEASE_SECONDS, job.job_id),
                )
                self._db.execute("COMMIT")
                return job, token
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

    def _finish(
        self, job: IndexJob, token: str, *,
        result: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> IndexJob:
        now = time.time()
        attempts = job.attempts + 1
        if result is not None:
            state = "completed"
            due = now
            detail = None
            encoded = json.dumps(result, sort_keys=True, allow_nan=False)
        else:
            # Retry after bounded local backoff; no background task is spawned.
            state = "failed" if attempts >= MAX_ATTEMPTS else "queued"
            due = now + 10 * (5 ** (attempts - 1))
            detail = f"{type(error).__name__}: {str(error)[:240]}"
            encoded = None
        with self._lock:
            cursor = self._db.execute(
                "UPDATE offline_index_jobs SET state=?, updated_at=?, next_due_at=?, "
                "lease_token=NULL, lease_until=NULL, last_error=?, result_json=? "
                "WHERE job_id=? AND state='running' AND lease_token=?",
                (state, now, due, detail, encoded, job.job_id, token),
            )
        if cursor.rowcount != 1:
            raise OfflineQueueError("index job lease ownership lost")
        return self.get(job.job_id)

    def _assert_live_lease(self, job_id: str, token: str) -> None:
        """Reject a stale worker before the document index transaction commits."""
        with self._lock:
            row = self._db.execute(
                "SELECT state,lease_token,lease_until FROM offline_index_jobs "
                "WHERE job_id=?", (job_id,),
            ).fetchone()
        if (
            row is None or row[0] != "running" or row[1] != token
            or type(row[2]) not in (int, float) or row[2] <= time.time()
        ):
            raise OfflineQueueError("index job lease ownership lost before commit")

    def run_one(self) -> IndexJob | None:
        """Perform one eligible bounded directory scan synchronously."""
        claimed = self._claim()
        if claimed is None:
            return None
        job, token = claimed
        try:
            with OfflineDocumentLibrary(job.library) as documents:
                result = documents.index_directory(
                    job.source,
                    before_commit=lambda: self._assert_live_lease(job.job_id, token),
                )
            return self._finish(job, token, result=result)
        except Exception as exc:
            return self._finish(job, token, error=exc)

    def drain(self, *, limit: int = MAX_RUN_BATCH) -> tuple[IndexJob, ...]:
        if type(limit) is not int or not 1 <= limit <= MAX_RUN_BATCH:
            raise OfflineQueueError("offline drain batch must contain 1-20 jobs")
        completed: list[IndexJob] = []
        for _ in range(limit):
            job = self.run_one()
            if job is None:
                break
            completed.append(job)
        return tuple(completed)


__all__ = [
    "SCHEMA", "IndexJob", "OfflineQueueError", "OfflineIndexQueue",
]
