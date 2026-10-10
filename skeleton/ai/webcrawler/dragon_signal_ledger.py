"""Durable, owner-scoped interest-signal ledger with retention and idempotency.

The ledger does not authorize discovery or video ingestion. The caller must
authenticate owner identity and obtain explicit consent before recording.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
import json
import sqlite3

from .dragon_interest_signals import (
    InterestSignal, SignalKind, SignalPolicy, InterestProfile,
    build_interest_profile, validate_signal,
)


@dataclass(frozen=True)
class SignalLedgerPolicy:
    max_per_owner: int = 5000
    retention_seconds: float = 90 * 86400
    max_batch: int = 256


class DragonSignalLedger:
    def __init__(self, connection: sqlite3.Connection, *, policy: SignalLedgerPolicy = SignalLedgerPolicy()):
        if not 1 <= policy.max_per_owner <= 100000:
            raise ValueError("invalid owner signal budget")
        if not 1 <= policy.max_batch <= 10000:
            raise ValueError("invalid batch budget")
        if not isfinite(policy.retention_seconds) or not 60 <= policy.retention_seconds <= 3650 * 86400:
            raise ValueError("invalid retention")
        self.connection = connection
        self.policy = policy
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS dragon_interest_signal (
                owner TEXT NOT NULL,
                signal_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                observed_at REAL NOT NULL,
                strength REAL NOT NULL,
                source_id TEXT NOT NULL,
                PRIMARY KEY(owner, signal_id)
            )
        """)
        self.connection.execute("""
            CREATE INDEX IF NOT EXISTS dragon_interest_signal_retention
            ON dragon_interest_signal(owner, observed_at)
        """)
        self.connection.commit()

    @staticmethod
    def _owner(owner: str) -> str:
        if not isinstance(owner, str) or not owner or len(owner) > 128:
            raise ValueError("invalid owner")
        return owner

    def append(self, owner: str, signals: tuple[InterestSignal, ...], *, now: float) -> int:
        owner = self._owner(owner)
        if not isfinite(now) or len(signals) > self.policy.max_batch:
            raise ValueError("invalid append request")
        if not signals:
            return 0
        checked = []
        for signal in signals:
            tags = validate_signal(signal, now, SignalPolicy())
            if now - signal.observed_at > self.policy.retention_seconds:
                raise ValueError("signal outside retention")
            checked.append((owner, signal.signal_id, signal.kind.value,
                            json.dumps(tags), signal.observed_at,
                            signal.strength, signal.source_id))
        # All-or-nothing batch: capacity is checked against distinct IDs.
        with self.connection:
            existing = self.connection.execute(
                "SELECT signal_id FROM dragon_interest_signal WHERE owner=?",
                (owner,),
            ).fetchall()
            known = {row[0] for row in existing}
            new_ids = {row[1] for row in checked if row[1] not in known}
            if len(known) + len(new_ids) > self.policy.max_per_owner:
                raise ValueError("owner signal budget exceeded")
            before = self.connection.total_changes
            self.connection.executemany("""
                INSERT OR IGNORE INTO dragon_interest_signal
                (owner, signal_id, kind, tags_json, observed_at, strength, source_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, checked)
            return self.connection.total_changes - before

    def recent(self, owner: str, *, limit: int | None = None) -> tuple[InterestSignal, ...]:
        owner = self._owner(owner)
        if limit is None:
            limit = min(500, self.policy.max_per_owner)
        if type(limit) is not int or not 1 <= limit <= self.policy.max_per_owner:
            raise ValueError("invalid query limit")
        rows = self.connection.execute("""
            SELECT signal_id, kind, tags_json, observed_at, strength, source_id
            FROM dragon_interest_signal WHERE owner=?
            ORDER BY observed_at DESC, signal_id LIMIT ?
        """, (owner, limit)).fetchall()
        return tuple(
            InterestSignal(row[0], SignalKind(row[1]), tuple(json.loads(row[2])),
                           row[3], row[4], row[5], True)
            for row in rows
        )

    def profile(self, owner: str, *, now: float, policy: SignalPolicy = SignalPolicy()) -> InterestProfile:
        # Explicit access to an already consented ledger is still caller-gated.
        return build_interest_profile(
            self.recent(owner, limit=min(policy.max_signals, self.policy.max_per_owner)),
            now=now, policy=policy,
        )

    def prune(self, owner: str, *, now: float) -> int:
        owner = self._owner(owner)
        if not isfinite(now):
            raise ValueError("invalid clock")
        with self.connection:
            cursor = self.connection.execute(
                "DELETE FROM dragon_interest_signal WHERE owner=? AND observed_at<?",
                (owner, now - self.policy.retention_seconds),
            )
            return cursor.rowcount

    def erase(self, owner: str) -> int:
        owner = self._owner(owner)
        with self.connection:
            cursor = self.connection.execute(
                "DELETE FROM dragon_interest_signal WHERE owner=?", (owner,),
            )
            return cursor.rowcount
