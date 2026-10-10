"""ArchiveX source revision propagation with fail-closed impact bounds.

Propagates a changed archived source to affected promoted claims and creates
a review-pending research signal. It never interprets a revision as proof that
the previous claim was false.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from .archivex import ArchiveX
from .archivex_dependencies import ArchiveXDependencyIndex
from .archivex_signal_index import ArchiveXSignalIndex, ResearchSignal, SignalKind
from .archivex_signals import ArchiveSignalKind, compare_snapshots


@dataclass(frozen=True)
class PropagationPolicy:
    max_affected_claims: int = 1000
    invalidate_changed_sources: bool = True
    require_manual_review: bool = True


@dataclass(frozen=True)
class PropagationReceipt:
    owner: str
    earlier_snapshot_id: str
    later_snapshot_id: str
    signal: ResearchSignal
    affected_claims: tuple[str, ...]
    invalidated: int
    fingerprint: str


class ArchiveXSignalPropagator:
    def __init__(self, archive: ArchiveX,
                 dependencies: ArchiveXDependencyIndex,
                 signals: ArchiveXSignalIndex,
                 *, policy: PropagationPolicy = PropagationPolicy()):
        if not (archive.db is dependencies.db is signals.db):
            raise ValueError("propagation requires one archival database")
        if not 1 <= policy.max_affected_claims <= 10000:
            raise ValueError("invalid propagation budget")
        self.archive = archive
        self.dependencies = dependencies
        self.signals = signals
        self.policy = policy

    def propagate(self, owner: str, *,
                  earlier_snapshot_id: str, later_snapshot_id: str,
                  now: float, authorized: bool) -> PropagationReceipt:
        if not authorized:
            raise PermissionError("source propagation requires authorization")
        earlier = self.archive.read(owner, earlier_snapshot_id, authorized=True)
        later = self.archive.read(owner, later_snapshot_id, authorized=True)
        if earlier is None or later is None:
            raise ValueError("both snapshots are required")
        comparison = compare_snapshots(earlier, later)
        if comparison.kind is ArchiveSignalKind.FIRST_SEEN:
            raise ValueError("cannot propagate a first-seen comparison")
        count = self.archive.db.execute("""
            SELECT COUNT(DISTINCT claim_id) FROM archivex_dependencies
            WHERE owner=? AND snapshot_id=?
        """, (owner, earlier_snapshot_id)).fetchone()[0]
        max_batch = min(self.policy.max_affected_claims,
                        self.dependencies.policy.max_batch)
        if count > max_batch:
            raise ValueError("affected claims exceed propagation budget")
        affected = self.dependencies.impacted(
            owner, earlier_snapshot_id, authorized=True,
            limit=max_batch,
        )
        changed = comparison.kind is not ArchiveSignalKind.UNCHANGED
        kind = SignalKind.REVISION if changed else SignalKind.CORROBORATION
        if len(comparison.source_url) > 240:
            raise ValueError("source URL exceeds signal subject budget")
        signal = self.signals.record(
            owner, kind=kind, subject=comparison.source_url,
            source_snapshot_id=later_snapshot_id,
            observed_at=later[0].observed_at, now=now,
            strength=1.0 if changed else 0.1,
            review_required=self.policy.require_manual_review,
            metadata={
                "earlier_snapshot": earlier_snapshot_id,
                "comparison": comparison.kind.value,
                "similarity": comparison.similarity,
            },
            authorized=True,
        )
        invalidated = 0
        if changed and self.policy.invalidate_changed_sources:
            for claim_id in affected:
                if self.dependencies.knowledge.invalidate(
                    owner, claim_id,
                    reason="source revised; evidence review required",
                    authorized=True,
                ):
                    invalidated += 1
        fingerprint = sha256(json.dumps(
            [owner, earlier_snapshot_id, later_snapshot_id,
             signal.signal_id, affected, invalidated],
            separators=(",", ":"),
        ).encode()).hexdigest()
        return PropagationReceipt(
            owner, earlier_snapshot_id, later_snapshot_id,
            signal, affected, invalidated, fingerprint,
        )
