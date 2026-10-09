"""Atomic ArchiveX knowledge persistence and provenance-aware retrieval.

The same SQLite transaction consumes an approved promotion receipt and writes
the resulting memory. This closes the receipt-consumed-but-memory-not-written
gap. Entries remain owner-scoped and can be invalidated when evidence changes.

This is a factual research memory, not a conversational or training-data store.
It stores only caller-supplied, human-reviewed summaries; it never treats
corroboration as a guarantee of truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
import json
import sqlite3
import threading

from .archivex_promotion import ArchiveXPromotionGate, PromotionReceipt


@dataclass(frozen=True)
class MemoryWritePolicy:
    max_summary_chars: int = 4000
    max_evidence_ids: int = 128
    max_memories_per_owner: int = 100000
    max_query_results: int = 100
    max_tag_count: int = 32


@dataclass(frozen=True)
class ArchivedKnowledge:
    owner: str
    claim_id: str
    summary: str
    evidence_ids: tuple[str, ...]
    tags: tuple[str, ...]
    verification_fingerprint: str
    registry_fingerprint: str
    receipt_id: str
    written_at: float
    content_digest: str
    active: bool
    invalidation_reason: str = ""


class ArchiveXKnowledgeStore:
    def __init__(self, gate: ArchiveXPromotionGate, *,
                 policy: MemoryWritePolicy = MemoryWritePolicy()):
        if not 1 <= policy.max_summary_chars <= 100000:
            raise ValueError("invalid summary budget")
        if not 2 <= policy.max_evidence_ids <= 10000:
            raise ValueError("invalid evidence budget")
        if not 1 <= policy.max_memories_per_owner <= 1000000:
            raise ValueError("invalid owner capacity")
        if not 1 <= policy.max_query_results <= 10000:
            raise ValueError("invalid query budget")
        if not 1 <= policy.max_tag_count <= 1000:
            raise ValueError("invalid tag budget")
        self.gate = gate
        self.db = gate.db
        self.policy = policy
        self._lock = threading.RLock()
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS archivex_knowledge (
                owner TEXT NOT NULL,
                claim_id TEXT NOT NULL,
                summary TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                verification_fingerprint TEXT NOT NULL,
                registry_fingerprint TEXT NOT NULL,
                receipt_id TEXT NOT NULL,
                written_at REAL NOT NULL,
                content_digest TEXT NOT NULL,
                active INTEGER NOT NULL CHECK(active IN (0,1)),
                invalidation_reason TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(owner, claim_id)
            )
        """)
        self.db.execute("""
            CREATE INDEX IF NOT EXISTS archivex_knowledge_recent
            ON archivex_knowledge(owner, active, written_at DESC, claim_id)
        """)
        self.db.commit()

    @staticmethod
    def _owner(value: str) -> str:
        if not isinstance(value, str) or not 1 <= len(value) <= 128:
            raise ValueError("invalid owner")
        return value

    @staticmethod
    def _digest(summary: str, evidence: tuple[str, ...],
                tags: tuple[str, ...], receipt: PromotionReceipt) -> str:
        payload = json.dumps({
            "claim": receipt.claim_id,
            "summary": summary,
            "evidence": evidence,
            "tags": tags,
            "verification": receipt.verification_fingerprint,
            "registry": receipt.registry_fingerprint,
            "receipt": receipt.receipt_id,
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return sha256(payload.encode("utf-8")).hexdigest()

    def _validate(self, summary: str, evidence_ids: tuple[str, ...],
                  tags: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
        if (not isinstance(summary, str) or not summary.strip() or
                len(summary) > self.policy.max_summary_chars):
            raise ValueError("invalid memory summary")
        if (not isinstance(evidence_ids, tuple) or
                not 2 <= len(evidence_ids) <= self.policy.max_evidence_ids or
                any(not isinstance(x, str) or not 1 <= len(x) <= 128
                    for x in evidence_ids)):
            raise ValueError("invalid evidence references")
        if (not isinstance(tags, tuple) or len(tags) > self.policy.max_tag_count or
                any(not isinstance(x, str) or not 1 <= len(x) <= 64
                    for x in tags)):
            raise ValueError("invalid memory tags")
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError("duplicate evidence references")
        return tuple(sorted(evidence_ids)), tuple(sorted(set(tags)))

    def persist(self, receipt: PromotionReceipt, *,
                summary: str, evidence_ids: tuple[str, ...],
                tags: tuple[str, ...] = (), now: float,
                consent: bool, authorized: bool) -> ArchivedKnowledge:
        if not consent or not authorized:
            raise PermissionError("memory persistence requires current authorization")
        self._owner(receipt.owner)
        if not isfinite(now) or now < receipt.issued_at:
            raise ValueError("invalid persistence time")
        evidence, normalized_tags = self._validate(summary, evidence_ids, tags)
        digest = self._digest(summary, evidence, normalized_tags, receipt)
        # BEGIN IMMEDIATE makes the receipt update and memory insertion a
        # single serializable SQLite write transaction. Any exception rolls
        # both back. No external callbacks run while the lock is held.
        with self._lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                count = self.db.execute("""
                    SELECT COUNT(*) FROM archivex_knowledge WHERE owner=?
                """, (receipt.owner,)).fetchone()[0]
                if count >= self.policy.max_memories_per_owner:
                    raise ValueError("owner memory capacity exceeded")
                row = self.db.execute("""
                    SELECT receipt_id FROM archivex_knowledge
                    WHERE owner=? AND claim_id=?
                """, (receipt.owner, receipt.claim_id)).fetchone()
                if row is not None:
                    raise ValueError("memory already exists; revoke before replacement")
                consumed = self.db.execute("""
                    UPDATE archivex_promotions SET consumed_at=?
                    WHERE owner=? AND claim_id=? AND receipt_id=?
                      AND verification_fingerprint=?
                      AND registry_fingerprint=? AND approval_id=?
                      AND issued_at=? AND consumed_at IS NULL
                """, (now, receipt.owner, receipt.claim_id, receipt.receipt_id,
                      receipt.verification_fingerprint, receipt.registry_fingerprint,
                      receipt.approval_id, receipt.issued_at))
                if consumed.rowcount != 1:
                    raise ValueError("promotion receipt missing, stale or already used")
                self.db.execute("""
                    INSERT INTO archivex_knowledge (
                        owner, claim_id, summary, evidence_json, tags_json,
                        verification_fingerprint, registry_fingerprint,
                        receipt_id, written_at, content_digest, active
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, (
                    receipt.owner, receipt.claim_id, summary,
                    json.dumps(evidence), json.dumps(normalized_tags),
                    receipt.verification_fingerprint, receipt.registry_fingerprint,
                    receipt.receipt_id, now, digest,
                ))
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise
        return ArchivedKnowledge(
            receipt.owner, receipt.claim_id, summary, evidence, normalized_tags,
            receipt.verification_fingerprint, receipt.registry_fingerprint,
            receipt.receipt_id, now, digest, True,
        )

    def _decode(self, row: tuple) -> ArchivedKnowledge:
        (owner, claim_id, summary, evidence_json, tags_json, verification,
         registry, receipt_id, written_at, digest, active, reason) = row
        evidence = tuple(json.loads(evidence_json))
        tags = tuple(json.loads(tags_json))
        receipt = PromotionReceipt(
            owner, claim_id, verification, registry, "", written_at, receipt_id,
        )
        expected = self._digest(summary, evidence, tags, receipt)
        if expected != digest:
            raise ValueError("knowledge integrity violation")
        return ArchivedKnowledge(
            owner, claim_id, summary, evidence, tags, verification, registry,
            receipt_id, written_at, digest, bool(active), reason,
        )

    def read(self, owner: str, claim_id: str, *,
             authorized: bool, include_inactive: bool = False
             ) -> ArchivedKnowledge | None:
        self._owner(owner)
        if not authorized:
            raise PermissionError("memory read requires authorization")
        if not isinstance(claim_id, str) or not claim_id:
            raise ValueError("invalid claim")
        row = self.db.execute("""
            SELECT owner, claim_id, summary, evidence_json, tags_json,
                   verification_fingerprint, registry_fingerprint, receipt_id,
                   written_at, content_digest, active, invalidation_reason
            FROM archivex_knowledge WHERE owner=? AND claim_id=?
        """, (owner, claim_id)).fetchone()
        if row is None:
            return None
        result = self._decode(row)
        return result if include_inactive or result.active else None

    def recent(self, owner: str, *, authorized: bool,
               limit: int = 20) -> tuple[ArchivedKnowledge, ...]:
        self._owner(owner)
        if not authorized:
            raise PermissionError("memory query requires authorization")
        if not 1 <= limit <= self.policy.max_query_results:
            raise ValueError("invalid result limit")
        rows = self.db.execute("""
            SELECT claim_id FROM archivex_knowledge
            WHERE owner=? AND active=1
            ORDER BY written_at DESC, claim_id LIMIT ?
        """, (owner, limit)).fetchall()
        return tuple(
            self.read(owner, claim_id, authorized=True)
            for (claim_id,) in rows
        )

    def invalidate(self, owner: str, claim_id: str, *,
                   reason: str, authorized: bool) -> bool:
        self._owner(owner)
        if not authorized:
            raise PermissionError("memory invalidation requires authorization")
        if not isinstance(reason, str) or not 1 <= len(reason) <= 500:
            raise ValueError("invalidation requires a reason")
        with self._lock, self.db:
            result = self.db.execute("""
                UPDATE archivex_knowledge
                SET active=0, invalidation_reason=?
                WHERE owner=? AND claim_id=? AND active=1
            """, (reason, owner, claim_id))
            return result.rowcount == 1

    def invalidate_registry(self, owner: str, *, current_fingerprint: str,
                            authorized: bool) -> int:
        self._owner(owner)
        if not authorized:
            raise PermissionError("registry revalidation requires authorization")
        if not isinstance(current_fingerprint, str) or len(current_fingerprint) != 64:
            raise ValueError("invalid registry fingerprint")
        with self._lock, self.db:
            result = self.db.execute("""
                UPDATE archivex_knowledge SET active=0,
                    invalidation_reason='provenance registry changed'
                WHERE owner=? AND active=1 AND registry_fingerprint!=?
            """, (owner, current_fingerprint))
            return result.rowcount

    def erase(self, owner: str, *, authorized: bool) -> int:
        self._owner(owner)
        if not authorized:
            raise PermissionError("erasure requires authorization")
        with self._lock, self.db:
            result = self.db.execute(
                "DELETE FROM archivex_knowledge WHERE owner=?", (owner,))
            return result.rowcount
