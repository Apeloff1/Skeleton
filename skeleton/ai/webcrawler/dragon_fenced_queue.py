"""Fenced worker claims for the dragon video digestion queue.

A lease token is bound to an individual claim, not merely to a proposal.
Workers must present the current token to complete a job. This prevents
a stale worker from committing after its lease has been reassigned.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from secrets import token_hex
import sqlite3

from .dragon_proposal_store import DragonProposalStore, ProposalRecord


@dataclass(frozen=True)
class FencedClaim:
    record: ProposalRecord
    token: str
    expires_at: float


class FencedDragonQueue:
    def __init__(self, store: DragonProposalStore):
        self.store = store
        self.db = store.db
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS dragon_video_claim_fences (
                owner TEXT NOT NULL,
                proposal_id TEXT NOT NULL,
                token TEXT NOT NULL,
                expires_at REAL NOT NULL,
                PRIMARY KEY (owner, proposal_id)
            )
        """)
        self.db.commit()

    def claim(
        self, owner: str, *, now: float, consent: bool,
        lease_seconds: float = 120, max_attempts: int = 3,
    ) -> FencedClaim | None:
        if not consent:
            raise PermissionError("claim requires current digestion consent")
        if not isfinite(now) or now < 0:
            raise ValueError("invalid claim clock")
        if not isfinite(lease_seconds) or not 1 <= lease_seconds <= 3600:
            raise ValueError("invalid lease duration")
        # The underlying queue performs an owner-scoped conditional transition.
        record = self.store.claim(
            owner, now=now, consent=True,
            lease_seconds=lease_seconds, max_attempts=max_attempts,
        )
        if record is None:
            return None
        token = token_hex(32)
        expires_at = now + lease_seconds
        with self.db:
            self.db.execute("""
                INSERT INTO dragon_video_claim_fences
                    (owner, proposal_id, token, expires_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(owner, proposal_id)
                DO UPDATE SET token=excluded.token, expires_at=excluded.expires_at
            """, (owner, record.proposal.proposal_id, token, expires_at))
        return FencedClaim(record, token, expires_at)

    def finish(
        self, claim: FencedClaim, *, now: float,
        succeeded: bool, consent: bool,
    ) -> bool:
        if not consent:
            raise PermissionError("completion requires current digestion consent")
        if not isfinite(now) or now < 0:
            raise ValueError("invalid completion clock")
        if now >= claim.expires_at:
            return False
        with self.db:
            result = self.db.execute("""
                DELETE FROM dragon_video_claim_fences
                WHERE owner=? AND proposal_id=? AND token=? AND expires_at>?
            """, (
                claim.record.owner, claim.record.proposal.proposal_id,
                claim.token, now,
            ))
            if result.rowcount != 1:
                return False
            # This transition is in the same SQLite transaction as fence removal.
            return self.store.finish(
                claim.record.owner, claim.record.proposal.proposal_id,
                now=now, succeeded=succeeded, consent=True,
            )

    def revoke_owner(self, owner: str) -> int:
        self.store._validate_owner(owner)
        with self.db:
            result = self.db.execute(
                "DELETE FROM dragon_video_claim_fences WHERE owner=?", (owner,)
            )
        return result.rowcount
