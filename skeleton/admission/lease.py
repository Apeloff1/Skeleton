"""Transactional local admission ledger; remote ref CAS remains mandatory."""
from __future__ import annotations

import math
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

# Strictly fewer than five admissions per rolling minute.
MAX_PUSHES_LAST_MINUTE = 4
LEASE_TTL_SECONDS = 60
_SCHEMA = 1


@dataclass(frozen=True)
class LeaseToken:
    lane: str
    head_sha: str
    actor: str
    issued_at: float
    expiry: float
    nonce: str


class AdmissionLease:
    """One host, trusted directory, shared SQLite file for all local writers.

    Each acquisition consumes one rolling-window slot, even if the caller
    crashes or abandons the push. No automatic replay is authorized.
    The remote operation must independently enforce the expected-head CAS.
    """

    def __init__(self, ledger_path: Path, *, clock: Callable[[], float] = time.time):
        self.ledger_path = Path(ledger_path)
        self.clock = clock
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._transaction(bootstrap=True) as db:
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if version == 0:
                    tables = db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                    if tables:
                        raise RuntimeError("unknown admission ledger schema")
                    db.execute(
                        "CREATE TABLE admission (nonce TEXT PRIMARY KEY, lane TEXT NOT NULL, "
                        "head_sha TEXT NOT NULL, actor TEXT NOT NULL, issued REAL NOT NULL, "
                        "expiry REAL NOT NULL, released INTEGER NOT NULL DEFAULT 0 "
                        "CHECK (released IN (0, 1)))"
                    )
                    db.execute("CREATE TABLE ledger_clock (id INTEGER PRIMARY KEY CHECK(id=1), ts REAL NOT NULL)")
                    db.execute("INSERT INTO ledger_clock VALUES (1, 0)")
                    db.execute("PRAGMA user_version=1")
                elif version != _SCHEMA:
                    raise RuntimeError("unknown admission ledger schema")
                self._now(db)
        except sqlite3.Error as exc:
            raise RuntimeError("admission ledger unavailable; fail closed") from exc

    @contextmanager
    def _transaction(self, *, bootstrap: bool = False) -> Iterator[sqlite3.Connection]:
        # Do not silently replace a ledger that disappears between operations.
        uri = self.ledger_path.resolve().as_uri() + ("?mode=rwc" if bootstrap else "?mode=rw")
        db = None
        try:
            db = sqlite3.connect(uri, uri=True, timeout=2.0, isolation_level=None)
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            if not bootstrap and db.execute("PRAGMA user_version").fetchone()[0] != _SCHEMA:
                raise RuntimeError("admission ledger schema mismatch; fail closed")
            yield db
            db.execute("COMMIT")
        except (sqlite3.Error, OSError) as exc:
            raise RuntimeError("admission ledger unavailable; fail closed") from exc
        finally:
            if db is not None:
                # Closing an uncommitted transaction rolls back all changes.
                db.close()

    def _now(self, db: sqlite3.Connection) -> float:
        now = self.clock()
        if type(now) not in (int, float) or not math.isfinite(now) or now < 0:
            raise RuntimeError("invalid admission clock; fail closed")
        row = db.execute("SELECT ts FROM ledger_clock WHERE id=1").fetchone()
        if row is None or not math.isfinite(row[0]) or now < row[0]:
            raise RuntimeError("admission clock regressed; fail closed")
        db.execute("UPDATE ledger_clock SET ts=? WHERE id=1", (now,))
        return float(now)

    @staticmethod
    def _label(value: str) -> str:
        if not isinstance(value, str) or not value or len(value) > 256 or value.strip() != value:
            raise ValueError("invalid admission identity")
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("invalid admission identity")
        return value

    def acquire(self, lane: str, expected_sha: str, actor: str) -> LeaseToken | None:
        lane, expected_sha, actor = map(self._label, (lane, expected_sha, actor))
        with self._transaction() as db:
            now = self._now(db)
            cutoff = now - LEASE_TTL_SECONDS
            db.execute("DELETE FROM admission WHERE issued <= ? AND expiry <= ?", (cutoff, now))
            if db.execute(
                "SELECT 1 FROM admission WHERE head_sha=? AND released=0 AND expiry>?",
                (expected_sha, now),
            ).fetchone():
                raise RuntimeError("concurrent mutation on expected SHA; fail closed")
            if db.execute("SELECT COUNT(*) FROM admission WHERE issued>?", (cutoff,)).fetchone()[0] >= MAX_PUSHES_LAST_MINUTE:
                return None
            token = LeaseToken(lane, expected_sha, actor, now, now + LEASE_TTL_SECONDS, uuid.uuid4().hex)
            db.execute(
                "INSERT INTO admission (nonce,lane,head_sha,actor,issued,expiry) VALUES (?,?,?,?,?,?)",
                (token.nonce, token.lane, token.head_sha, token.actor, token.issued_at, token.expiry),
            )
            return token

    def release(self, token: LeaseToken, actual_sha: str) -> None:
        """Consume a live token once; actual_sha is the CAS precondition head."""
        if not isinstance(token, LeaseToken) or token.head_sha != actual_sha:
            raise RuntimeError("SHA mismatch on release; fail closed")
        with self._transaction() as db:
            now = self._now(db)
            updated = db.execute(
                "UPDATE admission SET released=1 WHERE nonce=? AND lane=? AND head_sha=? "
                "AND actor=? AND issued=? AND expiry=? AND released=0 AND expiry>?",
                (token.nonce, token.lane, token.head_sha, token.actor,
                 token.issued_at, token.expiry, now),
            )
            if updated.rowcount != 1:
                raise RuntimeError("unknown, expired or consumed admission; fail closed")

    def count_recent(self) -> int:
        """Count reserved admissions, including incomplete and abandoned ones."""
        with self._transaction() as db:
            now = self._now(db)
            return int(db.execute(
                "SELECT COUNT(*) FROM admission WHERE issued>?",
                (now - LEASE_TTL_SECONDS,),
            ).fetchone()[0])
