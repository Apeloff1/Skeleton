"""ArchiveX durable research signal index.

Signals are observations with provenance, not truth labels. Every signal is
scoped to an owner, tied to an archived source, bounded by an expiration time,
and optionally marked as requiring manual review. The index supports
deterministic decay, negative evidence, and time-window filtering.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from math import exp, isfinite
import json
import re
import sqlite3


class SignalKind(str, Enum):
    DISCOVERY = "discovery"
    CITATION = "citation"
    REVISION = "revision"
    RETRACTION = "retraction"
    CORROBORATION = "corroboration"
    CONTRADICTION = "contradiction"
    USER_INTEREST = "user_interest"


@dataclass(frozen=True)
class SignalIndexPolicy:
    max_signals_per_owner: int = 100000
    max_signal_age_days: int = 3650
    half_life_days: float = 90
    max_query_results: int = 100
    min_strength: float = 0.001


@dataclass(frozen=True)
class ResearchSignal:
    signal_id: str
    owner: str
    kind: SignalKind
    subject: str
    source_snapshot_id: str
    observed_at: float
    strength: float
    review_required: bool
    metadata_digest: str


@dataclass(frozen=True)
class ScoredResearchSignal:
    signal: ResearchSignal
    decayed_strength: float


class ArchiveXSignalIndex:
    def __init__(self, db: sqlite3.Connection, *,
                 policy: SignalIndexPolicy = SignalIndexPolicy()):
        if not 1 <= policy.max_signals_per_owner <= 10000000:
            raise ValueError("invalid signal capacity")
        if not 1 <= policy.max_signal_age_days <= 36500:
            raise ValueError("invalid signal retention")
        if not isfinite(policy.half_life_days) or policy.half_life_days <= 0:
            raise ValueError("invalid signal half-life")
        if not 1 <= policy.max_query_results <= 10000:
            raise ValueError("invalid query capacity")
        if not isfinite(policy.min_strength) or not 0 <= policy.min_strength <= 1:
            raise ValueError("invalid minimum signal strength")
        self.db = db
        self.policy = policy
        db.execute("""
            CREATE TABLE IF NOT EXISTS archivex_research_signals (
                owner TEXT NOT NULL,
                signal_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                subject TEXT NOT NULL,
                source_snapshot_id TEXT NOT NULL,
                observed_at REAL NOT NULL,
                strength REAL NOT NULL,
                review_required INTEGER NOT NULL,
                metadata_digest TEXT NOT NULL,
                PRIMARY KEY(owner, signal_id)
            )
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS archivex_signal_subject
            ON archivex_research_signals(owner, subject, observed_at DESC)
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS archivex_signal_source
            ON archivex_research_signals(owner, source_snapshot_id)
        """)
        db.commit()

    @staticmethod
    def _owner(owner: str) -> str:
        if not isinstance(owner, str) or not 1 <= len(owner) <= 128:
            raise ValueError("invalid signal owner")
        return owner

    @staticmethod
    def _digest(kind: SignalKind, subject: str, snapshot: str,
                observed_at: float, strength: float,
                review_required: bool, metadata: dict) -> tuple[str, str]:
        metadata_json = json.dumps(
            metadata, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        )
        metadata_digest = sha256(metadata_json.encode()).hexdigest()
        payload = json.dumps(
            [kind.value, subject, snapshot, observed_at, strength,
             review_required, metadata_digest],
            separators=(",", ":"), ensure_ascii=True, allow_nan=False,
        )
        return sha256(payload.encode()).hexdigest(), metadata_digest

    def record(self, owner: str, *, kind: SignalKind, subject: str,
               source_snapshot_id: str, observed_at: float, now: float,
               strength: float, review_required: bool = True,
               metadata: dict | None = None,
               authorized: bool) -> ResearchSignal:
        owner = self._owner(owner)
        if not authorized:
            raise PermissionError("signal recording requires authorization")
        if not isinstance(kind, SignalKind):
            raise ValueError("invalid signal kind")
        if not isinstance(subject, str) or not 1 <= len(subject) <= 240:
            raise ValueError("invalid signal subject")
        subject = " ".join(subject.casefold().split())
        if not subject:
            raise ValueError("empty signal subject")
        if (not isinstance(source_snapshot_id, str) or
                not re.fullmatch(r"[a-f0-9]{64}", source_snapshot_id)):
            raise ValueError("signal requires archived source identifier")
        if not isfinite(now) or not isfinite(observed_at):
            raise ValueError("invalid signal clock")
        if observed_at > now or now - observed_at > self.policy.max_signal_age_days * 86400:
            raise ValueError("signal outside retention window")
        if not isfinite(strength) or not 0 < strength <= 1:
            raise ValueError("invalid signal strength")
        if not isinstance(review_required, bool):
            raise ValueError("invalid review flag")
        metadata = metadata or {}
        if not isinstance(metadata, dict) or len(metadata) > 32:
            raise ValueError("invalid signal metadata")
        signal_id, metadata_digest = self._digest(
            kind, subject, source_snapshot_id, observed_at, strength,
            review_required, metadata,
        )
        with self.db:
            count = self.db.execute("""
                SELECT COUNT(*) FROM archivex_research_signals WHERE owner=?
            """, (owner,)).fetchone()[0]
            existing = self.db.execute("""
                SELECT 1 FROM archivex_research_signals
                WHERE owner=? AND signal_id=?
            """, (owner, signal_id)).fetchone()
            if not existing and count >= self.policy.max_signals_per_owner:
                raise ValueError("signal capacity exceeded")
            self.db.execute("""
                INSERT OR IGNORE INTO archivex_research_signals
                (owner, signal_id, kind, subject, source_snapshot_id,
                 observed_at, strength, review_required, metadata_digest)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                owner, signal_id, kind.value, subject, source_snapshot_id,
                observed_at, strength, int(review_required), metadata_digest,
            ))
        return ResearchSignal(
            signal_id, owner, kind, subject, source_snapshot_id,
            observed_at, strength, review_required, metadata_digest,
        )

    @staticmethod
    def _from_row(row: tuple) -> ResearchSignal:
        owner, signal_id, kind, subject, snapshot, observed, strength, review, digest = row
        return ResearchSignal(
            signal_id, owner, SignalKind(kind), subject, snapshot,
            observed, strength, bool(review), digest,
        )

    def query(self, owner: str, *, now: float, authorized: bool,
              subject: str | None = None, limit: int = 30,
              include_review_pending: bool = False
              ) -> tuple[ScoredResearchSignal, ...]:
        owner = self._owner(owner)
        if not authorized:
            raise PermissionError("signal query requires authorization")
        if not isfinite(now):
            raise ValueError("invalid signal clock")
        if not 1 <= limit <= self.policy.max_query_results:
            raise ValueError("invalid query limit")
        if subject is not None:
            if not isinstance(subject, str) or not 1 <= len(subject) <= 240:
                raise ValueError("invalid signal subject filter")
            subject = " ".join(subject.casefold().split())
        clauses = ["owner=?", "observed_at<=?", "observed_at>=?"]
        args = [owner, now, now - self.policy.max_signal_age_days * 86400]
        if subject is not None:
            clauses.append("subject=?")
            args.append(subject)
        if not include_review_pending:
            clauses.append("review_required=0")
        sql = ("""
            SELECT owner, signal_id, kind, subject, source_snapshot_id,
                   observed_at, strength, review_required, metadata_digest
            FROM archivex_research_signals WHERE """ +
            " AND ".join(clauses) +
            " ORDER BY observed_at DESC, signal_id LIMIT ?")
        args.append(self.policy.max_query_results * 10)
        rows = self.db.execute(sql, args).fetchall()
        scored = []
        for row in rows:
            signal = self._from_row(row)
            age_days = (now - signal.observed_at) / 86400
            score = signal.strength * exp(
                -0.6931471805599453 * age_days / self.policy.half_life_days
            )
            if score >= self.policy.min_strength:
                scored.append(ScoredResearchSignal(signal, round(score, 8)))
        scored.sort(key=lambda item: (
            -item.decayed_strength, item.signal.subject,
            item.signal.signal_id,
        ))
        return tuple(scored[:limit])

    def prune(self, owner: str, *, now: float, authorized: bool) -> int:
        owner = self._owner(owner)
        if not authorized:
            raise PermissionError("signal pruning requires authorization")
        if not isfinite(now):
            raise ValueError("invalid pruning clock")
        with self.db:
            result = self.db.execute("""
                DELETE FROM archivex_research_signals
                WHERE owner=? AND observed_at<?
            """, (owner, now - self.policy.max_signal_age_days * 86400))
            return result.rowcount

    def erase(self, owner: str, *, authorized: bool) -> int:
        owner = self._owner(owner)
        if not authorized:
            raise PermissionError("signal erasure requires authorization")
        with self.db:
            result = self.db.execute("""
                DELETE FROM archivex_research_signals WHERE owner=?
            """, (owner,))
            return result.rowcount
