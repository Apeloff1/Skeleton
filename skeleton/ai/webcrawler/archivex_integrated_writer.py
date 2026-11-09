"""ArchiveX integrated promotion and indexed memory persistence.

This is the mandatory high-assurance entry point for new ArchiveX memories.
The operation verifies that each promoted evidence identifier has a valid
archival anchor, consumes a one-use approval receipt, writes the memory and
indexes its source dependencies in a single SQLite transaction.

Do not call the lower-level knowledge store directly in high-assurance mode.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
import json
import sqlite3
import threading

from .archivex_dependencies import ArchiveXDependencyIndex
from .archivex_knowledge import ArchiveXKnowledgeStore, ArchivedKnowledge
from .archivex_lineage import ArchiveXEvidenceLineage, EvidenceAnchor
from .archivex_promotion import PromotionReceipt


@dataclass(frozen=True)
class IntegratedWritePolicy:
    max_evidence: int = 128
    require_unique_snapshots: bool = True
    require_current_archive: bool = True


@dataclass(frozen=True)
class IntegratedWriteReceipt:
    memory: ArchivedKnowledge
    snapshot_ids: tuple[str, ...]
    dependency_count: int
    lineage_fingerprint: str


class ArchiveXIntegratedWriter:
    def __init__(self, knowledge: ArchiveXKnowledgeStore,
                 lineage: ArchiveXEvidenceLineage,
                 dependencies: ArchiveXDependencyIndex,
                 *, policy: IntegratedWritePolicy = IntegratedWritePolicy()):
        if not (knowledge.db is lineage.db is dependencies.db):
            raise ValueError("integrated writer requires one SQLite connection")
        if not 2 <= policy.max_evidence <= 10000:
            raise ValueError("invalid integrated evidence budget")
        self.db = knowledge.db
        self.knowledge = knowledge
        self.lineage = lineage
        self.dependencies = dependencies
        self.policy = policy
        self._lock = threading.RLock()

    def _check_anchors(
        self, receipt: PromotionReceipt, evidence_ids: tuple[str, ...],
    ) -> tuple[tuple[str, str], ...]:
        records = []
        for evidence_id in evidence_ids:
            row = self.db.execute("""
                SELECT snapshot_id, start_byte, end_byte, excerpt_digest
                FROM archivex_evidence_anchors
                WHERE owner=? AND claim_id=? AND evidence_id=?
            """, (receipt.owner, receipt.claim_id, evidence_id)).fetchone()
            if row is None:
                raise ValueError("unanchored evidence cannot be promoted")
            anchor = EvidenceAnchor(receipt.claim_id, evidence_id, *row)
            check = self.lineage.validate(
                receipt.owner, anchor, authorized=True,
            )
            if not check.valid:
                raise ValueError("evidence anchor integrity failure: " + check.reason)
            snapshot = self.lineage.archive.read(
                receipt.owner, anchor.snapshot_id, authorized=True,
            )
            if snapshot is None:
                raise ValueError("archived evidence missing")
            if self.policy.require_current_archive:
                newest = self.lineage.archive.timeline(
                    receipt.owner, snapshot[0].source_url,
                    authorized=True, limit=1,
                )
                if newest and newest[0].content_digest != snapshot[0].content_digest:
                    raise ValueError("archived source changed since verification")
            records.append((evidence_id, anchor.snapshot_id))
        if self.policy.require_unique_snapshots:
            if len({snapshot for _, snapshot in records}) != len(records):
                raise ValueError("independent evidence must use distinct snapshots")
        return tuple(sorted(records))

    def persist(
        self, receipt: PromotionReceipt, *,
        summary: str, evidence_ids: tuple[str, ...],
        tags: tuple[str, ...] = (), now: float,
        consent: bool, authorized: bool,
    ) -> IntegratedWriteReceipt:
        if not authorized or not consent:
            raise PermissionError("integrated memory write requires current consent")
        if not isinstance(receipt, PromotionReceipt):
            raise ValueError("invalid promotion receipt")
        if not isfinite(now) or now < receipt.issued_at:
            raise ValueError("invalid persistence clock")
        if not 2 <= len(evidence_ids) <= self.policy.max_evidence:
            raise ValueError("invalid evidence count")
        evidence, normalized_tags = self.knowledge._validate(
            summary, evidence_ids, tags,
        )
        digest = self.knowledge._digest(
            summary, evidence, normalized_tags, receipt,
        )
        # BEGIN IMMEDIATE prevents concurrent writes on other connections
        # from changing the source state during this transaction.
        with self._lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                records = self._check_anchors(receipt, evidence)
                count = self.db.execute("""
                    SELECT COUNT(*) FROM archivex_knowledge WHERE owner=?
                """, (receipt.owner,)).fetchone()[0]
                if count >= self.knowledge.policy.max_memories_per_owner:
                    raise ValueError("memory capacity exceeded")
                existing = self.db.execute("""
                    SELECT 1 FROM archivex_knowledge
                    WHERE owner=? AND claim_id=?
                """, (receipt.owner, receipt.claim_id)).fetchone()
                if existing:
                    raise ValueError("claim already persisted")
                consumed = self.db.execute("""
                    UPDATE archivex_promotions SET consumed_at=?
                    WHERE owner=? AND claim_id=? AND receipt_id=?
                      AND verification_fingerprint=?
                      AND registry_fingerprint=? AND approval_id=?
                      AND issued_at=? AND consumed_at IS NULL
                """, (
                    now, receipt.owner, receipt.claim_id, receipt.receipt_id,
                    receipt.verification_fingerprint, receipt.registry_fingerprint,
                    receipt.approval_id, receipt.issued_at,
                ))
                if consumed.rowcount != 1:
                    raise ValueError("promotion receipt stale or already consumed")
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
                for evidence_id, snapshot_id in records:
                    self.db.execute("""
                        INSERT INTO archivex_dependencies
                        (owner, snapshot_id, claim_id, evidence_id)
                        VALUES (?, ?, ?, ?)
                    """, (
                        receipt.owner, snapshot_id, receipt.claim_id, evidence_id,
                    ))
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise
        memory = self.knowledge.read(
            receipt.owner, receipt.claim_id, authorized=True,
        )
        lineage_fingerprint = sha256(json.dumps(
            [receipt.receipt_id, records],
            separators=(",", ":"), ensure_ascii=True,
        ).encode()).hexdigest()
        return IntegratedWriteReceipt(
            memory, tuple(snapshot for _, snapshot in records),
            len(records), lineage_fingerprint,
        )

    def audit_claim(self, owner: str, claim_id: str, *,
                    authorized: bool) -> tuple[str, ...]:
        if not authorized:
            raise PermissionError("memory audit requires authorization")
        memory = self.knowledge.read(
            owner, claim_id, authorized=True, include_inactive=True,
        )
        if memory is None:
            return ("knowledge missing",)
        issues = []
        indexed = self.db.execute("""
            SELECT evidence_id, snapshot_id FROM archivex_dependencies
            WHERE owner=? AND claim_id=?
        """, (owner, claim_id)).fetchall()
        indexed_by_id = dict(indexed)
        for evidence_id in memory.evidence_ids:
            row = self.db.execute("""
                SELECT snapshot_id, start_byte, end_byte, excerpt_digest
                FROM archivex_evidence_anchors
                WHERE owner=? AND claim_id=? AND evidence_id=?
            """, (owner, claim_id, evidence_id)).fetchone()
            if row is None:
                issues.append("missing anchor: " + evidence_id)
                continue
            if indexed_by_id.get(evidence_id) != row[0]:
                issues.append("dependency mismatch: " + evidence_id)
            validation = self.lineage.validate(
                owner, EvidenceAnchor(claim_id, evidence_id, *row),
                authorized=True,
            )
            if not validation.valid:
                issues.append("invalid anchor: " + evidence_id)
        if set(indexed_by_id) != set(memory.evidence_ids):
            issues.append("dependency set mismatch")
        return tuple(sorted(issues))
