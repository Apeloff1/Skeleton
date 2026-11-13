"""Atomic cross-plane evidence handoffs for Jeeves / Builder / Dragon.

A handoff references an EXISTING verified source checkpoint and the target's
durable identity. It conveys facts and provenance only; it does not authorize
execution, training promotion, copying unlicensed content or accepting build
artifacts. Canonical subsystem verifiers remain required for consumption.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .annual_production import (
    AnnualProductionStore, ProductionConflict, _name, _digest, _clock, _hash,
    SCHEMA,
)

@dataclass(frozen=True)
class AnnualHandoff:
    source_id: str
    target_id: str
    source_system: str
    target_system: str
    source_sequence: int
    source_receipt_digest: str
    target_objective_digest: str
    review_evidence_digest: str
    previous_handoff_digest: str | None
    handoff_digest: str
    accepted_at: float


class AnnualHandoffLedger:
    """Shared persistent storage boundary for cross-domain digest receipts."""

    def __init__(self, store: AnnualProductionStore):
        self.store = store
        with self.store._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS annual_handoffs(
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                source_system TEXT NOT NULL,
                target_system TEXT NOT NULL,
                source_sequence INTEGER NOT NULL,
                source_receipt_digest TEXT NOT NULL,
                target_objective_digest TEXT NOT NULL,
                review_evidence_digest TEXT NOT NULL,
                previous_handoff_digest TEXT,
                handoff_digest TEXT NOT NULL,
                accepted_at REAL NOT NULL,
                PRIMARY KEY (source_id, target_id, source_sequence)
            )""")
            db.execute("""CREATE INDEX IF NOT EXISTS annual_handoff_target_idx
                ON annual_handoffs(target_id, accepted_at, source_id)""")

    def handoff(self, *, source_id: str, target_id: str,
                source_sequence: int, source_receipt_digest: str,
                review_evidence_digest: str, now: float,
                verify_review: Callable[[str, str, str, str], bool]) -> AnnualHandoff:
        source_id = _name(source_id, "source")
        target_id = _name(target_id, "target")
        if source_id == target_id:
            raise ValueError("cannot handoff into the same production")
        if type(source_sequence) is not int or source_sequence < 1:
            raise ValueError("invalid source sequence")
        receipt = _digest(source_receipt_digest, "source receipt")
        evidence = _digest(review_evidence_digest, "review evidence")
        at = _clock(now)
        if not callable(verify_review) or verify_review(source_id, target_id, receipt, evidence) is not True:
            raise PermissionError("trusted evidence review is required")
        # Verify the full immutable chain outside the write lock, then re-check
        # its exact head inside the transaction to fence racing checkpoint work.
        self.store.verify_chain(source_id)
        with self.store._tx() as db:
            source = self.store._row(db, source_id)
            target = self.store._row(db, target_id)
            if source["system"] == target["system"] or target["status"] in (
                "completed", "failed", "cancelled"
            ):
                raise ProductionConflict("invalid cross-system handoff")
            if (source["sequence"] != source_sequence or
                    source["last_receipt_digest"] != receipt):
                raise ProductionConflict("source checkpoint no longer current")
            db.row_factory = None
            existing = db.execute("""SELECT * FROM annual_handoffs
                WHERE source_id=? AND target_id=? AND source_sequence=?""",
                (source_id, target_id, source_sequence)).fetchone()
            if existing:
                seen = AnnualHandoff(*existing)
                if seen.source_receipt_digest != receipt or seen.review_evidence_digest != evidence:
                    raise ProductionConflict("conflicting handoff receipt")
                return seen
            previous = db.execute("""SELECT handoff_digest FROM annual_handoffs
                WHERE source_id=? AND target_id=?
                ORDER BY source_sequence DESC LIMIT 1""", (source_id, target_id)).fetchone()
            prior_digest = previous[0] if previous else None
            data = {"schema": SCHEMA, "source_id": source_id, "target_id": target_id,
                    "source_system": source["system"], "target_system": target["system"],
                    "source_sequence": source_sequence,
                    "source_receipt_digest": receipt,
                    "target_objective_digest": target["objective_digest"],
                    "review_evidence_digest": evidence,
                    "previous_handoff_digest": prior_digest,
                    "accepted_at": at}
            digest = _hash(data)
            handoff = AnnualHandoff(
                source_id, target_id, source["system"], target["system"],
                source_sequence, receipt, target["objective_digest"], evidence,
                prior_digest, digest, at,
            )
            db.execute("""INSERT INTO annual_handoffs VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                tuple(handoff.__dict__.values()))
            return handoff

    def list_for(self, target_id: str, *, limit: int = 32) -> tuple[AnnualHandoff, ...]:
        target_id = _name(target_id, "target")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("invalid handoff page size")
        with self.store._connect() as db:
            return tuple(AnnualHandoff(*row) for row in db.execute("""
                SELECT * FROM annual_handoffs WHERE target_id=?
                ORDER BY accepted_at DESC, source_id DESC LIMIT ?""", (target_id, limit)))

    def verify(self, source_id: str, target_id: str) -> int:
        source_id, target_id = _name(source_id, "source"), _name(target_id, "target")
        with self.store._connect() as db:
            count, previous, last_sequence = 0, None, 0
            cursor = db.execute("""SELECT * FROM annual_handoffs
                WHERE source_id=? AND target_id=? ORDER BY source_sequence""",
                (source_id, target_id))
            for raw in cursor:
                h = AnnualHandoff(*raw)
                if h.source_sequence <= last_sequence or h.previous_handoff_digest != previous:
                    raise ProductionConflict("handoff chain ordering failure")
                data = {"schema": SCHEMA, "source_id": h.source_id,
                        "target_id": h.target_id, "source_system": h.source_system,
                        "target_system": h.target_system, "source_sequence": h.source_sequence,
                        "source_receipt_digest": h.source_receipt_digest,
                        "target_objective_digest": h.target_objective_digest,
                        "review_evidence_digest": h.review_evidence_digest,
                        "previous_handoff_digest": h.previous_handoff_digest,
                        "accepted_at": h.accepted_at}
                if _hash(data) != h.handoff_digest:
                    raise ProductionConflict("handoff history integrity failure")
                previous, last_sequence, count = h.handoff_digest, h.source_sequence, count + 1
            return count
