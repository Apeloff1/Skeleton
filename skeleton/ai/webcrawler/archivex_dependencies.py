"""ArchiveX claim-level dependency index and targeted invalidation.

A reverse index maps immutable source snapshots to promoted claims, avoiding
full memory scans when one source changes. It is owner-scoped and designed for
deterministic, bounded batch processing.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import sqlite3

from .archivex_knowledge import ArchiveXKnowledgeStore
from .archivex_lineage import ArchiveXEvidenceLineage


@dataclass(frozen=True)
class DependencyPolicy:
    max_claims_per_snapshot: int = 10000
    max_batch: int = 1000


@dataclass(frozen=True)
class InvalidationReceipt:
    owner: str
    snapshot_id: str
    affected_claims: tuple[str, ...]
    invalidated: int
    fingerprint: str


class ArchiveXDependencyIndex:
    def __init__(self, lineage: ArchiveXEvidenceLineage,
                 knowledge: ArchiveXKnowledgeStore,
                 *, policy: DependencyPolicy = DependencyPolicy()):
        if lineage.db is not knowledge.db:
            raise ValueError("dependency index requires shared SQLite database")
        if not 1 <= policy.max_claims_per_snapshot <= 100000:
            raise ValueError("invalid dependency capacity")
        if not 1 <= policy.max_batch <= 10000:
            raise ValueError("invalid dependency batch")
        self.db = lineage.db
        self.lineage = lineage
        self.knowledge = knowledge
        self.policy = policy
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS archivex_dependencies (
                owner TEXT NOT NULL,
                snapshot_id TEXT NOT NULL,
                claim_id TEXT NOT NULL,
                evidence_id TEXT NOT NULL,
                PRIMARY KEY(owner, snapshot_id, claim_id, evidence_id)
            )
        """)
        self.db.execute("""
            CREATE INDEX IF NOT EXISTS archivex_dependency_claim
            ON archivex_dependencies(owner, claim_id)
        """)
        self.db.commit()

    def index_claim(self, owner: str, claim_id: str, *,
                    authorized: bool) -> int:
        if not authorized:
            raise PermissionError("dependency indexing requires authorization")
        self.lineage.archive._owner(owner)
        memory = self.knowledge.read(owner, claim_id, authorized=True)
        if memory is None:
            raise ValueError("active knowledge not found")
        records = []
        for evidence_id in memory.evidence_ids:
            row = self.db.execute("""
                SELECT snapshot_id FROM archivex_evidence_anchors
                WHERE owner=? AND claim_id=? AND evidence_id=?
            """, (owner, claim_id, evidence_id)).fetchone()
            if row is None:
                raise ValueError("missing archived evidence anchor")
            records.append((owner, row[0], claim_id, evidence_id))
        with self.db:
            self.db.execute("""
                DELETE FROM archivex_dependencies
                WHERE owner=? AND claim_id=?
            """, (owner, claim_id))
            self.db.executemany("""
                INSERT INTO archivex_dependencies
                (owner, snapshot_id, claim_id, evidence_id)
                VALUES (?, ?, ?, ?)
            """, records)
        return len(records)

    def impacted(self, owner: str, snapshot_id: str, *,
                 authorized: bool, limit: int | None = None
                 ) -> tuple[str, ...]:
        if not authorized:
            raise PermissionError("dependency lookup requires authorization")
        self.lineage.archive._owner(owner)
        limit = self.policy.max_batch if limit is None else limit
        if not 1 <= limit <= self.policy.max_batch:
            raise ValueError("invalid impact limit")
        rows = self.db.execute("""
            SELECT DISTINCT claim_id FROM archivex_dependencies
            WHERE owner=? AND snapshot_id=?
            ORDER BY claim_id LIMIT ?
        """, (owner, snapshot_id, limit)).fetchall()
        return tuple(row[0] for row in rows)

    def invalidate_snapshot(self, owner: str, snapshot_id: str, *,
                            reason: str, authorized: bool
                            ) -> InvalidationReceipt:
        if not authorized:
            raise PermissionError("dependency invalidation requires authorization")
        if not isinstance(reason, str) or not 1 <= len(reason) <= 200:
            raise ValueError("invalidation reason required")
        count = self.db.execute("""
            SELECT COUNT(DISTINCT claim_id) FROM archivex_dependencies
            WHERE owner=? AND snapshot_id=?
        """, (owner, snapshot_id)).fetchone()[0]
        if count > self.policy.max_batch:
            raise ValueError("impact exceeds batch budget; paginate first")
        claims = self.impacted(owner, snapshot_id, authorized=True)
        invalidated = 0
        for claim_id in claims:
            if self.knowledge.invalidate(
                owner, claim_id, reason=reason, authorized=True,
            ):
                invalidated += 1
        fingerprint = sha256(json.dumps(
            [owner, snapshot_id, claims, reason],
            separators=(",", ":"), ensure_ascii=True,
        ).encode("utf-8")).hexdigest()
        return InvalidationReceipt(
            owner, snapshot_id, claims, invalidated, fingerprint,
        )

    def erase(self, owner: str, *, authorized: bool) -> int:
        if not authorized:
            raise PermissionError("dependency erasure requires authorization")
        self.lineage.archive._owner(owner)
        with self.db:
            cursor = self.db.execute(
                "DELETE FROM archivex_dependencies WHERE owner=?", (owner,))
            return cursor.rowcount
