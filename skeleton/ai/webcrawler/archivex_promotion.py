"""ArchiveX knowledge promotion: fail-closed, evidence-bound receipts.

A corroborated label alone cannot write memory. Promotion requires a complete
anchored verification, a pinned policy/registry fingerprint, explicit human
approval, and an owner-scoped one-time receipt. This is an authorization gate,
not a memory backend; callers must use its receipt at the persistence boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
import json
import sqlite3

from .archivex_truth_gate import AnchoredVerification
from .dragon_truth_verifier import VerificationStatus


@dataclass(frozen=True)
class PromotionPolicy:
    max_approved_claims: int = 10000
    require_explicit_approval: bool = True
    min_accepted_evidence: int = 2


@dataclass(frozen=True)
class PromotionReceipt:
    owner: str
    claim_id: str
    verification_fingerprint: str
    registry_fingerprint: str
    approval_id: str
    issued_at: float
    receipt_id: str


class ArchiveXPromotionGate:
    def __init__(self, db: sqlite3.Connection, *,
                 policy: PromotionPolicy = PromotionPolicy()):
        if not 1 <= policy.max_approved_claims <= 1000000:
            raise ValueError("invalid promotion capacity")
        if not 2 <= policy.min_accepted_evidence <= 1000:
            raise ValueError("at least two archived evidence items required")
        self.db = db
        self.policy = policy
        db.execute("""
            CREATE TABLE IF NOT EXISTS archivex_promotions (
                owner TEXT NOT NULL,
                claim_id TEXT NOT NULL,
                verification_fingerprint TEXT NOT NULL,
                registry_fingerprint TEXT NOT NULL,
                approval_id TEXT NOT NULL,
                issued_at REAL NOT NULL,
                receipt_id TEXT NOT NULL,
                consumed_at REAL,
                PRIMARY KEY (owner, claim_id),
                UNIQUE (owner, receipt_id)
            )
        """)
        db.commit()

    @staticmethod
    def _identity(owner: str, claim_id: str, verification: str,
                  registry: str, approval: str, now: float) -> str:
        payload = json.dumps(
            [owner, claim_id, verification, registry, approval, now],
            separators=(",", ":"), ensure_ascii=True, allow_nan=False,
        )
        return sha256(payload.encode("utf-8")).hexdigest()

    def authorize(
        self, owner: str, result: AnchoredVerification, *,
        claim_id: str, approval_id: str, now: float,
        consent: bool, reviewer_approved: bool,
    ) -> PromotionReceipt:
        if not consent:
            raise PermissionError("memory promotion requires current consent")
        if not reviewer_approved and self.policy.require_explicit_approval:
            raise PermissionError("memory promotion requires human approval")
        if not isinstance(owner, str) or not owner or len(owner) > 128:
            raise ValueError("invalid owner")
        if not isinstance(claim_id, str) or not claim_id or len(claim_id) > 128:
            raise ValueError("invalid claim")
        if not isinstance(approval_id, str) or not approval_id or len(approval_id) > 128:
            raise ValueError("invalid approval identifier")
        if not isfinite(now) or now < 0:
            raise ValueError("invalid clock")
        verification = result.provenance.result
        if verification.claim_id != claim_id:
            raise ValueError("verification belongs to another claim")
        if not result.archive_checked:
            raise ValueError("archive verification missing")
        if result.invalid_anchor_ids or result.missing_anchor_ids:
            raise ValueError("incomplete evidence lineage")
        if verification.status is not VerificationStatus.CORROBORATED:
            raise ValueError("claim is not corroborated")
        if (len(set(result.accepted_evidence_ids)) < self.policy.min_accepted_evidence or
                verification.independent_supporters < 2):
            raise ValueError("insufficient independent anchored evidence")
        if result.provenance.accepted_sources < self.policy.min_accepted_evidence:
            raise ValueError("provenance coverage insufficient")
        fingerprint = verification.fingerprint
        registry = result.provenance.registry_fingerprint
        receipt_id = self._identity(
            owner, claim_id, fingerprint, registry, approval_id, now,
        )
        with self.db:
            count = self.db.execute(
                "SELECT COUNT(*) FROM archivex_promotions WHERE owner=?",
                (owner,),
            ).fetchone()[0]
            existing = self.db.execute("""
                SELECT verification_fingerprint, registry_fingerprint,
                       approval_id, issued_at, receipt_id
                FROM archivex_promotions WHERE owner=? AND claim_id=?
            """, (owner, claim_id)).fetchone()
            if existing:
                if existing != (fingerprint, registry, approval_id, now, receipt_id):
                    raise ValueError("conflicting promotion requires explicit revocation")
            elif count >= self.policy.max_approved_claims:
                raise ValueError("promotion capacity exceeded")
            else:
                self.db.execute("""
                    INSERT INTO archivex_promotions
                    (owner, claim_id, verification_fingerprint,
                     registry_fingerprint, approval_id, issued_at, receipt_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (owner, claim_id, fingerprint, registry, approval_id, now, receipt_id))
        return PromotionReceipt(
            owner, claim_id, fingerprint, registry, approval_id, now, receipt_id,
        )

    def consume(self, receipt: PromotionReceipt, *, now: float,
                consent: bool) -> bool:
        if not consent:
            raise PermissionError("memory persistence requires current consent")
        if not isfinite(now) or now < receipt.issued_at:
            raise ValueError("invalid consumption time")
        with self.db:
            result = self.db.execute("""
                UPDATE archivex_promotions SET consumed_at=?
                WHERE owner=? AND claim_id=? AND receipt_id=?
                  AND verification_fingerprint=? AND registry_fingerprint=?
                  AND approval_id=? AND issued_at=? AND consumed_at IS NULL
            """, (now, receipt.owner, receipt.claim_id, receipt.receipt_id,
                  receipt.verification_fingerprint, receipt.registry_fingerprint,
                  receipt.approval_id, receipt.issued_at))
            return result.rowcount == 1

    def revoke(self, owner: str, claim_id: str | None = None) -> int:
        if not isinstance(owner, str) or not owner or len(owner) > 128:
            raise ValueError("invalid owner")
        with self.db:
            if claim_id is None:
                result = self.db.execute(
                    "DELETE FROM archivex_promotions WHERE owner=?", (owner,))
            else:
                result = self.db.execute("""
                    DELETE FROM archivex_promotions WHERE owner=? AND claim_id=?
                """, (owner, claim_id))
            return result.rowcount
