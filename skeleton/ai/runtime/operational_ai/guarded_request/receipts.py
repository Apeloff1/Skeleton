"""Durable external-effect intent receipts; generation receipts remain in OfflineChatStore.

A prepared intent cannot be silently retried after ambiguous side effects.
Only reconciliation against an independently verified effect may finish it.
"""
from __future__ import annotations

import sqlite3
from threading import RLock

from .contracts import canonical_bytes
from .errors import deny
from .identities import require_id
from .model_pins import require_sha256


class EffectReceipts:
    def __init__(self, db: sqlite3.Connection):
        self.db = db
        self._lock = RLock()
        db.execute("""CREATE TABLE IF NOT EXISTS guarded_effect_receipts(
            scope TEXT NOT NULL, effect_id TEXT NOT NULL, args_sha TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('prepared','committed','aborted')),
            receipt_json BLOB, PRIMARY KEY(scope,effect_id))""")

    def prepare(self, *, scope: str, effect_id: str, args_sha: str) -> str:
        require_id(scope, "scope")
        require_id(effect_id, "effect")
        require_sha256(args_sha)
        with self._lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                prior = self.db.execute(
                    "SELECT args_sha,state FROM guarded_effect_receipts WHERE scope=? AND effect_id=?",
                    (scope, effect_id),
                ).fetchone()
                if prior:
                    if prior[0] != args_sha:
                        deny("effect-arguments-conflict")
                    self.db.execute("COMMIT")
                    return prior[1]
                self.db.execute(
                    """INSERT INTO guarded_effect_receipts(scope,effect_id,args_sha,state)
                    VALUES(?,?,?,'prepared')""",
                    (scope, effect_id, args_sha),
                )
                self.db.execute("COMMIT")
                return "prepared"
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def close(
        self,
        *,
        scope: str,
        effect_id: str,
        args_sha: str,
        committed: bool,
        verified_receipt: dict,
    ) -> str:
        require_id(scope, "scope")
        require_id(effect_id, "effect")
        require_sha256(args_sha)
        data = canonical_bytes(verified_receipt)
        state = "committed" if committed else "aborted"
        with self._lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                row = self.db.execute(
                    "SELECT args_sha,state,receipt_json FROM guarded_effect_receipts WHERE scope=? AND effect_id=?",
                    (scope, effect_id),
                ).fetchone()
                if row is None or row[0] != args_sha:
                    deny("effect-no-intent")
                if row[1] != "prepared":
                    if row[1] != state or row[2] != data:
                        deny("effect-terminal-conflict")
                    self.db.execute("COMMIT")
                    return "replayed"
                self.db.execute(
                    """UPDATE guarded_effect_receipts SET state=?,receipt_json=?
                    WHERE scope=? AND effect_id=? AND state='prepared'""",
                    (state, data, scope, effect_id),
                )
                self.db.execute("COMMIT")
                return state
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def pending(self, scope: str) -> list[dict]:
        require_id(scope, "scope")
        rows = self.db.execute(
            """SELECT effect_id,args_sha FROM guarded_effect_receipts
            WHERE scope=? AND state='prepared' ORDER BY effect_id""", (scope,)
        ).fetchall()
        return [{"effect_id": row[0], "args_sha": row[1]} for row in rows]
