"""Transactional monotonic anti-replay fence for authenticated request envelopes.

A same-nonce, same-sequence, same-payload repetition is a replay *only*;
no second action or inference is implied by the response.
"""
from __future__ import annotations

import sqlite3
from threading import RLock

from .contracts import strict_integer
from .errors import deny
from .identities import require_id
from .model_pins import require_sha256


class NonceFence:
    def __init__(self, db: sqlite3.Connection):
        self.db = db
        self._lock = RLock()
        db.execute("""CREATE TABLE IF NOT EXISTS guarded_nonce_heads(
            scope TEXT PRIMARY KEY, sequence INTEGER NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS guarded_nonce_events(
            scope TEXT NOT NULL, nonce TEXT NOT NULL, sequence INTEGER NOT NULL,
            payload_sha TEXT NOT NULL, PRIMARY KEY(scope, nonce))""")

    def reserve(self, scope: str, nonce: str, sequence: int, payload_sha: str) -> str:
        require_id(scope, "scope")
        require_id(nonce, "nonce")
        strict_integer(sequence, minimum=1, maximum=2**63 - 1, field="sequence")
        require_sha256(payload_sha)
        with self._lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                old = self.db.execute(
                    "SELECT sequence,payload_sha FROM guarded_nonce_events WHERE scope=? AND nonce=?",
                    (scope, nonce),
                ).fetchone()
                if old is not None:
                    if old != (sequence, payload_sha):
                        deny("nonce-collision")
                    self.db.execute("COMMIT")
                    return "replayed"
                head = self.db.execute(
                    "SELECT sequence FROM guarded_nonce_heads WHERE scope=?", (scope,)
                ).fetchone()
                if head is not None and sequence <= head[0]:
                    deny("nonce-out-of-order")
                self.db.execute(
                    "INSERT INTO guarded_nonce_events(scope,nonce,sequence,payload_sha) VALUES(?,?,?,?)",
                    (scope, nonce, sequence, payload_sha),
                )
                self.db.execute(
                    """INSERT INTO guarded_nonce_heads(scope,sequence) VALUES(?,?)
                    ON CONFLICT(scope) DO UPDATE SET sequence=excluded.sequence""",
                    (scope, sequence),
                )
                self.db.execute("COMMIT")
                return "admitted"
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def head(self, scope: str) -> int:
        require_id(scope, "scope")
        row = self.db.execute(
            "SELECT sequence FROM guarded_nonce_heads WHERE scope=?", (scope,)
        ).fetchone()
        return 0 if row is None else row[0]
