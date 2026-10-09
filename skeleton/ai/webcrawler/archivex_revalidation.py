"""ArchiveX revision-triggered knowledge invalidation.

A source revision does not prove an earlier claim false. It *does* make an
earlier verification stale. This component conservatively invalidates
memories whose archived evidence snapshots were superseded, deleted, or
integrity-compromised. Reinstatement requires a fresh verification receipt.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import sqlite3

from .archivex import ArchiveX
from .archivex_knowledge import ArchiveXKnowledgeStore
from .archivex_lineage import ArchiveXEvidenceLineage
from .archivex_signals import ArchiveSignalKind, source_drift_timeline


@dataclass(frozen=True)
class RevalidationPolicy:
    max_claims_per_pass: int = 500
    max_source_snapshots: int = 100
    invalidate_on_revision: bool = True
    invalidate_on_missing_archive: bool = True


@dataclass(frozen=True)
class RevalidationEvent:
    claim_id: str
    evidence_id: str
    snapshot_id: str
    reason: str


@dataclass(frozen=True)
class RevalidationReport:
    owner: str
    inspected: int
    invalidated: int
    events: tuple[RevalidationEvent, ...]
    fingerprint: str


class ArchiveXRevalidator:
    def __init__(self, archive: ArchiveX,
                 lineage: ArchiveXEvidenceLineage,
                 knowledge: ArchiveXKnowledgeStore,
                 *, policy: RevalidationPolicy = RevalidationPolicy()):
        if not 1 <= policy.max_claims_per_pass <= 10000:
            raise ValueError("invalid revalidation claim budget")
        if not 2 <= policy.max_source_snapshots <= 1000:
            raise ValueError("invalid revalidation snapshot budget")
        if archive.db is not lineage.db or archive.db is not knowledge.db:
            raise ValueError("revalidation requires a shared archival database")
        self.archive = archive
        self.lineage = lineage
        self.knowledge = knowledge
        self.policy = policy

    def run(self, owner: str, *, authorized: bool) -> RevalidationReport:
        if not authorized:
            raise PermissionError("revalidation requires authorization")
        owner = self.archive._owner(owner)
        rows = self.knowledge.db.execute("""
            SELECT claim_id FROM archivex_knowledge
            WHERE owner=? AND active=1
            ORDER BY claim_id LIMIT ?
        """, (owner, self.policy.max_claims_per_pass)).fetchall()
        events = []
        invalidated = 0
        for (claim_id,) in rows:
            memory = self.knowledge.read(owner, claim_id, authorized=True)
            if memory is None:
                continue
            reasons = []
            for evidence_id in memory.evidence_ids:
                row = self.lineage.db.execute("""
                    SELECT snapshot_id, start_byte, end_byte, excerpt_digest
                    FROM archivex_evidence_anchors
                    WHERE owner=? AND claim_id=? AND evidence_id=?
                """, (owner, claim_id, evidence_id)).fetchone()
                if row is None:
                    reasons.append(RevalidationEvent(
                        claim_id, evidence_id, "", "evidence anchor missing",
                    ))
                    continue
                from .archivex_lineage import EvidenceAnchor
                anchor = EvidenceAnchor(claim_id, evidence_id, *row)
                validation = self.lineage.validate(
                    owner, anchor, authorized=True,
                )
                if not validation.valid:
                    reasons.append(RevalidationEvent(
                        claim_id, evidence_id, anchor.snapshot_id,
                        validation.reason,
                    ))
                    continue
                if not self.policy.invalidate_on_revision:
                    continue
                snapshot = self.archive.read(
                    owner, anchor.snapshot_id, authorized=True,
                )
                if snapshot is None:
                    reasons.append(RevalidationEvent(
                        claim_id, evidence_id, anchor.snapshot_id,
                        "archived source missing",
                    ))
                    continue
                meta = snapshot[0]
                latest = self.archive.timeline(
                    owner, meta.source_url, authorized=True, limit=1,
                )
                if latest and latest[0].snapshot_id != anchor.snapshot_id:
                    # Compare actual digests; recapture of identical content
                    # should not trigger needless invalidation.
                    if latest[0].content_digest != meta.content_digest:
                        reasons.append(RevalidationEvent(
                            claim_id, evidence_id, anchor.snapshot_id,
                            "newer source snapshot changed",
                        ))
            if reasons:
                reason = "; ".join(sorted({event.reason for event in reasons}))
                if self.knowledge.invalidate(
                    owner, claim_id, reason=reason, authorized=True,
                ):
                    invalidated += 1
                events.extend(reasons)
        ordered = tuple(sorted(
            events, key=lambda e: (
                e.claim_id, e.evidence_id, e.snapshot_id, e.reason,
            ),
        ))
        fingerprint = sha256(json.dumps(
            [(e.claim_id, e.evidence_id, e.snapshot_id, e.reason)
             for e in ordered],
            separators=(",", ":"),
        ).encode()).hexdigest()
        return RevalidationReport(owner, len(rows), invalidated,
                                  ordered, fingerprint)
