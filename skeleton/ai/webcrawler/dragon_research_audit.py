"""Deterministic audit receipts for video research decisions.

Receipts are chained per owner, with canonical JSON and strict event budgets.
No video contents or secret credentials are written to the audit ledger.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import sqlite3
from math import isfinite


@dataclass(frozen=True)
class ResearchAuditEvent:
    owner: str
    sequence: int
    action: str
    subject_id: str
    observed_at: float
    previous_hash: str
    event_hash: str


class DragonResearchAudit:
    ACTIONS = frozenset({
        "proposal_created", "proposal_approved", "proposal_rejected",
        "lease_claimed", "lease_expired", "digest_completed",
        "digest_failed", "consent_revoked", "history_erased",
    })

    def __init__(self, connection: sqlite3.Connection):
        self.db = connection
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS dragon_research_audit (
                owner TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                action TEXT NOT NULL,
                subject_id TEXT NOT NULL,
                observed_at REAL NOT NULL,
                previous_hash TEXT NOT NULL,
                event_hash TEXT NOT NULL,
                PRIMARY KEY (owner, sequence)
            )
        """)
        self.db.commit()

    @staticmethod
    def _digest(owner: str, sequence: int, action: str,
                subject_id: str, observed_at: float, previous_hash: str) -> str:
        payload = json.dumps(
            [owner, sequence, action, subject_id, observed_at, previous_hash],
            ensure_ascii=True, separators=(",", ":"), allow_nan=False,
        )
        return sha256(payload.encode("utf-8")).hexdigest()

    def append(self, owner: str, action: str, subject_id: str,
               *, now: float) -> ResearchAuditEvent:
        if not isinstance(owner, str) or not owner or len(owner) > 128:
            raise ValueError("invalid owner")
        if action not in self.ACTIONS:
            raise ValueError("unsupported audit action")
        if not isinstance(subject_id, str) or not subject_id or len(subject_id) > 128:
            raise ValueError("invalid audit subject")
        if isinstance(now, bool) or not isinstance(now, (int, float)) or not isfinite(now) or now < 0:
            raise ValueError("invalid audit time")
        now = float(now)
        with self.db:
            row = self.db.execute("""
                SELECT sequence, event_hash FROM dragon_research_audit
                WHERE owner=? ORDER BY sequence DESC LIMIT 1
            """, (owner,)).fetchone()
            sequence = row[0] + 1 if row else 1
            previous = row[1] if row else "0" * 64
            digest = self._digest(owner, sequence, action, subject_id, now, previous)
            self.db.execute("""
                INSERT INTO dragon_research_audit
                (owner, sequence, action, subject_id, observed_at, previous_hash, event_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (owner, sequence, action, subject_id, now, previous, digest))
        return ResearchAuditEvent(owner, sequence, action, subject_id, now, previous, digest)

    def verify(self, owner: str, *, max_events: int = 100000) -> bool:
        if not isinstance(owner, str) or not owner or len(owner) > 128:
            raise ValueError("invalid owner")
        if not 1 <= max_events <= 1000000:
            raise ValueError("invalid verification budget")
        rows = self.db.execute("""
            SELECT sequence, action, subject_id, observed_at, previous_hash, event_hash
            FROM dragon_research_audit WHERE owner=? ORDER BY sequence
            LIMIT ?
        """, (owner, max_events + 1)).fetchall()
        if len(rows) > max_events:
            raise ValueError("audit verification budget exceeded")
        previous = "0" * 64
        for expected, row in enumerate(rows, 1):
            sequence, action, subject_id, timestamp, stored_previous, digest = row
            if sequence != expected or stored_previous != previous:
                return False
            if digest != self._digest(owner, sequence, action, subject_id,
                                      timestamp, stored_previous):
                if not float(timestamp).is_integer() or digest != self._digest(
                        owner, sequence, action, subject_id, int(timestamp), stored_previous):
                    return False
            previous = digest
        return True

    def erase(self, owner: str) -> int:
        if not isinstance(owner, str) or not owner or len(owner) > 128:
            raise ValueError("invalid owner")
        with self.db:
            result = self.db.execute(
                "DELETE FROM dragon_research_audit WHERE owner=?", (owner,)
            )
        return result.rowcount
