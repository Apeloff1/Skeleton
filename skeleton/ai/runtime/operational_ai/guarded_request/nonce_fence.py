"""Transactional monotonic anti-replay fence for authenticated request envelopes.

A same-nonce, same-sequence, same-payload repetition is a replay *only*;
no second action or inference is implied by the response.
"""
from __future__ import annotations

import sqlite3
from threading import RLock

from .contracts import strict_integer
from .errors import deny
from .identities import Scope, require_id
from .model_pins import require_sha256


def _scope_key(scope: Scope | str) -> str:
    if type(scope) is Scope:
        return scope.key
    if type(scope) is str and "/" in scope:
        parts = scope.split("/")
        if len(parts) != 4:
            deny("scope-invalid")
        return Scope(*parts).key
    # Retain historical single-label namespaces for existing local callers.
    return require_id(scope, "scope")


class NonceFence:
    def __init__(self, db: sqlite3.Connection):
        self.db = db
        self._lock = RLock()
        self._poisoned = False
        db.execute("""CREATE TABLE IF NOT EXISTS guarded_nonce_heads(
            scope TEXT PRIMARY KEY, sequence INTEGER NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS guarded_nonce_events(
            scope TEXT NOT NULL, nonce TEXT NOT NULL, sequence INTEGER NOT NULL,
            payload_sha TEXT NOT NULL, PRIMARY KEY(scope, nonce))""")

    def reserve(self, scope: Scope | str, nonce: str, sequence: int, payload_sha: str) -> str:
        scope = _scope_key(scope)
        require_id(nonce, "nonce")
        strict_integer(sequence, minimum=1, maximum=2**63 - 1, field="sequence")
        require_sha256(payload_sha)
        with self._lock:
            if self._poisoned:
                deny("nonce-fence-unavailable")
            try:
                self.db.execute("BEGIN IMMEDIATE")
            except sqlite3.Error:
                deny("nonce-transaction-admission")
            try:
                old = self.db.execute(
                    "SELECT sequence,payload_sha FROM guarded_nonce_events WHERE scope=? AND nonce=?",
                    (scope, nonce),
                ).fetchone()
                if old is not None:
                    if (old[0], old[1]) != (sequence, payload_sha):
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
                if self.db.in_transaction:
                    try:
                        self.db.execute("ROLLBACK")
                    except sqlite3.Error:
                        self._poisoned = True
                        deny("nonce-transaction-rollback")
                raise

    def head(self, scope: Scope | str) -> int:
        scope = _scope_key(scope)
        # Serialize observations with reservations on this connection; callers
        # must not share it with independently synchronized writers.
        with self._lock:
            if self._poisoned:
                deny("nonce-fence-unavailable")
            row = self.db.execute(
                "SELECT sequence FROM guarded_nonce_heads WHERE scope=?", (scope,)
            ).fetchone()
            return 0 if row is None else row[0]
