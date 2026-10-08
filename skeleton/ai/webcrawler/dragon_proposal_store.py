"""Owner-scoped durable video discovery proposals with lease-safe claiming.

The store tracks metadata proposals only. It never fetches, downloads, or
processes media. An authorized worker must separately verify user consent.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
import sqlite3

from .dragon_video_discovery import VideoProposal


@dataclass(frozen=True)
class ProposalRecord:
    owner: str
    proposal: VideoProposal
    state: str
    created_at: float
    updated_at: float
    lease_until: float | None
    attempts: int


class DragonProposalStore:
    STATES = frozenset({"pending", "approved", "leased", "completed", "rejected"})

    def __init__(self, connection: sqlite3.Connection):
        self.db = connection
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS dragon_video_proposals (
                owner TEXT NOT NULL,
                proposal_id TEXT NOT NULL,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                reason TEXT NOT NULL,
                score REAL NOT NULL,
                tags_json TEXT NOT NULL,
                state TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                lease_until REAL,
                attempts INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(owner, proposal_id)
            )
        """)
        self.db.execute("""
            CREATE INDEX IF NOT EXISTS dragon_video_proposals_queue
            ON dragon_video_proposals(owner, state, updated_at)
        """)
        self.db.commit()

    @staticmethod
    def _validate_owner(owner: str) -> None:
        if not isinstance(owner, str) or not owner or len(owner) > 128:
            raise ValueError("invalid owner")

    @staticmethod
    def _validate_clock(now: float) -> None:
        if not isfinite(now) or now < 0:
            raise ValueError("invalid clock")

    def enqueue(self, owner: str, proposals: tuple[VideoProposal, ...], *,
                now: float, consent: bool, max_pending: int = 100) -> int:
        import json
        self._validate_owner(owner)
        self._validate_clock(now)
        if not consent:
            raise PermissionError("proposal retention requires consent")
        if not 1 <= max_pending <= 1000 or len(proposals) > max_pending:
            raise ValueError("invalid proposal budget")
        for item in proposals:
            if not item.requires_approval or not isfinite(item.score):
                raise ValueError("unapproved or invalid proposal")
        with self.db:
            active = {row[0] for row in self.db.execute("""
                SELECT proposal_id FROM dragon_video_proposals
                WHERE owner=? AND state IN ('pending', 'approved', 'leased')
            """, (owner,)).fetchall()}
            existing_ids = {row[0] for row in self.db.execute("""
                SELECT proposal_id FROM dragon_video_proposals WHERE owner=?
            """, (owner,)).fetchall()}
            new_ids = {p.proposal_id for p in proposals} - existing_ids
            if len(active) + len(new_ids) > max_pending:
                raise ValueError("proposal queue capacity exceeded")
            before = self.db.total_changes
            self.db.executemany("""
                INSERT OR IGNORE INTO dragon_video_proposals
                (owner, proposal_id, url, title, reason, score, tags_json,
                 state, created_at, updated_at, lease_until, attempts)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, NULL, 0)
            """, [
                (owner, p.proposal_id, p.url, p.title, p.reason, p.score,
                 json.dumps(p.shared_tags), now, now) for p in proposals
            ])
            return self.db.total_changes - before

    def decide(self, owner: str, proposal_id: str, *, approve: bool,
               now: float, consent: bool) -> bool:
        self._validate_owner(owner)
        self._validate_clock(now)
        if not consent:
            raise PermissionError("proposal review requires consent")
        with self.db:
            result = self.db.execute("""
                UPDATE dragon_video_proposals
                SET state=?, updated_at=?
                WHERE owner=? AND proposal_id=? AND state='pending'
            """, ("approved" if approve else "rejected", now, owner, proposal_id))
            return result.rowcount == 1

    def claim(self, owner: str, *, now: float, lease_seconds: float = 120,
              consent: bool, max_attempts: int = 3) -> ProposalRecord | None:
        self._validate_owner(owner)
        self._validate_clock(now)
        if not consent:
            raise PermissionError("digestion requires current authorization")
        if not isfinite(lease_seconds) or not 1 <= lease_seconds <= 3600:
            raise ValueError("invalid lease duration")
        if not 1 <= max_attempts <= 100:
            raise ValueError("invalid attempt budget")
        with self.db:
            row = self.db.execute("""
                SELECT proposal_id FROM dragon_video_proposals
                WHERE owner=? AND (
                    state='approved' OR
                    (state='leased' AND lease_until<=?)
                ) AND attempts<?
                ORDER BY updated_at, proposal_id LIMIT 1
            """, (owner, now, max_attempts)).fetchone()
            if row is None:
                return None
            result = self.db.execute("""
                UPDATE dragon_video_proposals
                SET state='leased', lease_until=?, attempts=attempts+1,
                    updated_at=?
                WHERE owner=? AND proposal_id=? AND (
                    state='approved' OR (state='leased' AND lease_until<=?)
                ) AND attempts<?
            """, (now + lease_seconds, now, owner, row[0], now, max_attempts))
            if result.rowcount != 1:
                return None
            return self.get(owner, row[0])

    def finish(self, owner: str, proposal_id: str, *, now: float,
               succeeded: bool, consent: bool) -> bool:
        self._validate_owner(owner)
        self._validate_clock(now)
        if not consent:
            raise PermissionError("completion requires current authorization")
        with self.db:
            result = self.db.execute("""
                UPDATE dragon_video_proposals
                SET state=?, updated_at=?, lease_until=NULL
                WHERE owner=? AND proposal_id=? AND state='leased'
                  AND lease_until>?
            """, ("completed" if succeeded else "approved",
                  now, owner, proposal_id, now))
            return result.rowcount == 1

    def get(self, owner: str, proposal_id: str) -> ProposalRecord | None:
        import json
        self._validate_owner(owner)
        row = self.db.execute("""
            SELECT url, title, reason, score, tags_json, state,
                   created_at, updated_at, lease_until, attempts
            FROM dragon_video_proposals
            WHERE owner=? AND proposal_id=?
        """, (owner, proposal_id)).fetchone()
        if row is None:
            return None
        proposal = VideoProposal(proposal_id, row[0], row[1], row[2],
                                 row[3], tuple(json.loads(row[4])), True)
        return ProposalRecord(owner, proposal, row[5], row[6], row[7],
                              row[8], row[9])

    def erase(self, owner: str) -> int:
        self._validate_owner(owner)
        with self.db:
            result = self.db.execute(
                "DELETE FROM dragon_video_proposals WHERE owner=?", (owner,))
            return result.rowcount
