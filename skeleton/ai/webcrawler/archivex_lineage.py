"""ArchiveX evidence lineage: bind claims to immutable snapshots.

Evidence links are validated against archived bytes and time. A source URL
alone is never enough to prove that a cited excerpt appeared in a snapshot.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
import json
import sqlite3

from .archivex import ArchiveX
from .dragon_truth_verifier import Claim, Evidence


@dataclass(frozen=True)
class EvidenceAnchor:
    claim_id: str
    evidence_id: str
    snapshot_id: str
    start_byte: int
    end_byte: int
    excerpt_digest: str


@dataclass(frozen=True)
class AnchorValidation:
    anchor: EvidenceAnchor
    valid: bool
    reason: str


class ArchiveXEvidenceLineage:
    def __init__(self, archive: ArchiveX):
        self.archive = archive
        self.db = archive.db
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS archivex_evidence_anchors (
                owner TEXT NOT NULL,
                claim_id TEXT NOT NULL,
                evidence_id TEXT NOT NULL,
                snapshot_id TEXT NOT NULL,
                start_byte INTEGER NOT NULL,
                end_byte INTEGER NOT NULL,
                excerpt_digest TEXT NOT NULL,
                PRIMARY KEY(owner, claim_id, evidence_id)
            )
        """)
        self.db.commit()

    @staticmethod
    def _check_id(value: str) -> None:
        if not isinstance(value, str) or not value or len(value) > 128:
            raise ValueError("invalid evidence identifier")

    def anchor(self, owner: str, claim: Claim, evidence: Evidence, *,
               snapshot_id: str, start_byte: int, end_byte: int,
               authorized: bool) -> EvidenceAnchor:
        if not authorized:
            raise PermissionError("anchoring requires archive authorization")
        self._check_id(claim.claim_id)
        self._check_id(evidence.evidence_id)
        if claim.claim_id != evidence.claim_id:
            raise ValueError("evidence references another claim")
        snapshot = self.archive.read(owner, snapshot_id, authorized=True)
        if snapshot is None:
            raise ValueError("unknown snapshot")
        meta, body = snapshot
        if meta.source_url != evidence.source_url:
            raise ValueError("source URL does not match archived source")
        if not isinstance(start_byte, int) or not isinstance(end_byte, int):
            raise ValueError("invalid byte offsets")
        if not 0 <= start_byte < end_byte <= len(body):
            raise ValueError("excerpt outside archived content")
        excerpt = body[start_byte:end_byte]
        if excerpt.decode("utf-8", errors="strict") != evidence.excerpt:
            raise ValueError("excerpt does not match archived bytes")
        digest = sha256(excerpt).hexdigest()
        with self.db:
            existing = self.db.execute("""
                SELECT snapshot_id, start_byte, end_byte, excerpt_digest
                FROM archivex_evidence_anchors
                WHERE owner=? AND claim_id=? AND evidence_id=?
            """, (owner, claim.claim_id, evidence.evidence_id)).fetchone()
            if existing is not None and existing != (
                snapshot_id, start_byte, end_byte, digest
            ):
                raise ValueError("evidence anchor conflict")
            self.db.execute("""
                INSERT OR IGNORE INTO archivex_evidence_anchors
                (owner, claim_id, evidence_id, snapshot_id,
                 start_byte, end_byte, excerpt_digest)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (owner, claim.claim_id, evidence.evidence_id,
                  snapshot_id, start_byte, end_byte, digest))
        return EvidenceAnchor(claim.claim_id, evidence.evidence_id,
                              snapshot_id, start_byte, end_byte, digest)

    def validate(self, owner: str, anchor: EvidenceAnchor, *,
                 authorized: bool) -> AnchorValidation:
        if not authorized:
            raise PermissionError("lineage verification requires authorization")
        row = self.db.execute("""
            SELECT snapshot_id, start_byte, end_byte, excerpt_digest
            FROM archivex_evidence_anchors
            WHERE owner=? AND claim_id=? AND evidence_id=?
        """, (owner, anchor.claim_id, anchor.evidence_id)).fetchone()
        if row is None or row != (
            anchor.snapshot_id, anchor.start_byte,
            anchor.end_byte, anchor.excerpt_digest,
        ):
            return AnchorValidation(anchor, False, "anchor record missing or changed")
        try:
            snapshot = self.archive.read(owner, anchor.snapshot_id, authorized=True)
        except ValueError:
            return AnchorValidation(anchor, False, "snapshot integrity failure")
        if snapshot is None:
            return AnchorValidation(anchor, False, "snapshot missing")
        body = snapshot[1]
        if not 0 <= anchor.start_byte < anchor.end_byte <= len(body):
            return AnchorValidation(anchor, False, "invalid byte range")
        digest = sha256(body[anchor.start_byte:anchor.end_byte]).hexdigest()
        if digest != anchor.excerpt_digest:
            return AnchorValidation(anchor, False, "excerpt integrity failure")
        return AnchorValidation(anchor, True, "archive evidence matches")

    def erase(self, owner: str) -> int:
        self.archive._owner(owner)
        with self.db:
            result = self.db.execute(
                "DELETE FROM archivex_evidence_anchors WHERE owner=?", (owner,)
            )
            return result.rowcount
