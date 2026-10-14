"""Durable compare-and-swap journal for Jeeves creator workflow execution.

The host injects an absolute private SQLite file path. A committed in-flight
intent survives process crashes and blocks replay until independently reconciled.
Append-only revisions anchor plan identity and every state transition.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any, Mapping

from .creator_runbook_runtime import CreatorRunbookError, _digest

MAX_REVISIONS = 8192
MAX_SNAPSHOT_BYTES = 256 * 1024

_SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS creator_runbook_revision (
    sequence INTEGER PRIMARY KEY,
    prior_head TEXT,
    head_digest TEXT NOT NULL UNIQUE,
    state_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS creator_runbook_meta (
    singleton INTEGER PRIMARY KEY CHECK (singleton=1),
    plan_sha256 TEXT NOT NULL,
    head_digest TEXT,
    revision_count INTEGER NOT NULL
);
"""


class CreatorRunbookStore:
    """Append-only host persistence adapter accepted by CreatorRunbookRunner."""

    def __init__(self, path: str | Path, *, plan_sha256: str) -> None:
        if (not isinstance(plan_sha256, str) or len(plan_sha256) != 64
                or any(c not in "0123456789abcdef" for c in plan_sha256)):
            raise CreatorRunbookError("store needs canonical creator plan SHA")
        self.path = Path(path)
        if not self.path.is_absolute():
            raise CreatorRunbookError("runbook store path must be host-absolute")
        self.plan_sha256 = plan_sha256
        self._lock = RLock()
        self._db = sqlite3.connect(
            str(self.path), timeout=10, isolation_level=None,
            check_same_thread=False,
        )
        try:
            self._db.execute("PRAGMA busy_timeout=10000")
            self._db.executescript(_SCHEMA)
            self._initialize()
        except BaseException:
            self._db.close()
            raise

    def _initialize(self) -> None:
        row = self._db.execute(
            "SELECT plan_sha256, head_digest, revision_count "
            "FROM creator_runbook_meta WHERE singleton=1"
        ).fetchone()
        if row is None:
            count = self._db.execute(
                "SELECT COUNT(*) FROM creator_runbook_revision"
            ).fetchone()[0]
            if count:
                raise CreatorRunbookError("runbook has journal without authority metadata")
            self._db.execute(
                "INSERT INTO creator_runbook_meta VALUES (1, ?, NULL, 0)",
                (self.plan_sha256,),
            )
        elif row[0] != self.plan_sha256:
            raise CreatorRunbookError("runbook store belongs to a different plan")
        self.load()

    def load(self) -> dict[str, Any] | None:
        """Validate the full revision chain and return its latest state."""
        with self._lock:
            meta = self._db.execute(
                "SELECT plan_sha256, head_digest, revision_count "
                "FROM creator_runbook_meta WHERE singleton=1"
            ).fetchone()
            if meta is None or meta[0] != self.plan_sha256:
                raise CreatorRunbookError("runbook authority metadata missing")
            expected_prior = None
            count = 0
            latest = None
            for sequence, prior, head, encoded in self._db.execute(
                "SELECT sequence, prior_head, head_digest, state_json "
                "FROM creator_runbook_revision ORDER BY sequence"
            ):
                if sequence != count or count >= MAX_REVISIONS or prior != expected_prior:
                    raise CreatorRunbookError("runbook revision sequence is broken")
                if (not isinstance(encoded, str)
                        or len(encoded.encode("utf-8")) > MAX_SNAPSHOT_BYTES):
                    raise CreatorRunbookError("persisted runbook exceeds size budget")
                try:
                    state = json.loads(encoded)
                except (TypeError, ValueError) as exc:
                    raise CreatorRunbookError("runbook state is not JSON") from exc
                if not isinstance(state, dict) or state.get("plan_sha256") != self.plan_sha256:
                    raise CreatorRunbookError("persisted runbook changed plan identity")
                proposed = dict(state)
                stated_head = proposed.pop("head_digest", None)
                if stated_head != head or _digest(proposed) != head:
                    raise CreatorRunbookError("runbook state digest mismatch")
                expected_prior = head
                latest = state
                count += 1
            if meta != (self.plan_sha256, expected_prior, count):
                raise CreatorRunbookError("runbook authority head diverges from journal")
            return latest

    def persist(self, state: Mapping[str, Any], expected_head: str | None) -> bool:
        """Commit a revision iff expected_head is the latest committed head.

        Fail closed: a stale writer is rejected without touching the journal.
        """
        if not isinstance(state, Mapping):
            raise CreatorRunbookError("runbook snapshot must be mapping")
        data = dict(state)
        if data.get("plan_sha256") != self.plan_sha256:
            raise CreatorRunbookError("cannot persist another plan")
        proposed = dict(data)
        head = proposed.pop("head_digest", None)
        if head != _digest(proposed):
            raise CreatorRunbookError("runbook snapshot content is unbound")
        encoded = json.dumps(data, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False)
        if len(encoded.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
            raise CreatorRunbookError("runbook revision exceeds size budget")
        with self._lock:
            try:
                self._db.execute("BEGIN IMMEDIATE")
                row = self._db.execute(
                    "SELECT head_digest, revision_count FROM creator_runbook_meta "
                    "WHERE singleton=1"
                ).fetchone()
                if row is None:
                    raise CreatorRunbookError("runbook authority metadata missing")
                active_head, count = row
                if active_head != expected_head or count >= MAX_REVISIONS:
                    self._db.execute("ROLLBACK")
                    return False
                self._db.execute(
                    "INSERT INTO creator_runbook_revision VALUES (?, ?, ?, ?)",
                    (count, active_head, head, encoded),
                )
                self._db.execute(
                    "UPDATE creator_runbook_meta SET head_digest=?, revision_count=? "
                    "WHERE singleton=1",
                    (head, count + 1),
                )
                self._db.execute("COMMIT")
                return True
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> "CreatorRunbookStore":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


__all__ = ["CreatorRunbookStore"]
