"""Provenance-preserving source reread scheduler and canonical claim ledger."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
import sqlite3

from .dragon_probabilistic_distillation import (
    EvidencePass, EvidencePolicy, Belief, ProbabilisticKnowledgeDistiller,
)


@dataclass(frozen=True)
class RereadTask:
    source_id: str
    source_revision: str
    pass_index: int
    lens: str
    required: bool


_LENSES = (
    "literal extraction",
    "mechanics and causal structure",
    "temporal ordering and state transitions",
    "counterexamples and contradictions",
    "uncertainty and alternative explanations",
    "provenance and copyright boundaries",
    "accessibility and player experience",
    "cross-source synthesis",
    "adversarial reinspection",
    "schema consistency and compression",
    "novelty and transferability",
    "final falsification review",
)


def schedule_rereads(source_id: str, source_revision: str, *,
                     minimum: int = 3, maximum: int = 8
                     ) -> tuple[RereadTask, ...]:
    if not isinstance(source_id, str) or not 1 <= len(source_id) <= 256:
        raise ValueError("invalid source identity")
    if not isinstance(source_revision, str) or not 1 <= len(source_revision) <= 128:
        raise ValueError("invalid source revision")
    if not 1 <= minimum <= maximum <= len(_LENSES):
        raise ValueError("invalid reread bounds")
    return tuple(RereadTask(
        source_id, source_revision, i + 1, _LENSES[i], i < minimum,
    ) for i in range(maximum))


class DragonKnowledgeLedger:
    """Immutable readings, canonical claims, owner-scoped deletion."""

    def __init__(self, db: sqlite3.Connection,
                 policy: EvidencePolicy = EvidencePolicy()):
        self.db = db
        self.distiller = ProbabilisticKnowledgeDistiller(policy)
        db.execute("""
            CREATE TABLE IF NOT EXISTS dragon_evidence_passes(
                owner TEXT NOT NULL, claim_id TEXT NOT NULL,
                source_id TEXT NOT NULL,source_revision TEXT NOT NULL,
                pass_id TEXT NOT NULL,supports INTEGER NOT NULL,
                confidence REAL NOT NULL,reliability REAL NOT NULL,
                independence_group TEXT NOT NULL,evidence_locator TEXT NOT NULL,
                observation TEXT NOT NULL,
                PRIMARY KEY(owner,source_id,source_revision,pass_id))
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS dragon_evidence_claim_idx
            ON dragon_evidence_passes(owner,claim_id)
        """)
        db.commit()

    def add(self, owner: str, item: EvidencePass, *,
            authorized: bool) -> None:
        if not authorized:
            raise PermissionError("evidence writing requires authorization")
        if not isinstance(owner, str) or not 1 <= len(owner) <= 128:
            raise ValueError("invalid owner")
        self.distiller._validate(item)
        with self.db:
            existing = self.db.execute("""
                SELECT claim_id,supports,confidence,reliability,
                       independence_group,evidence_locator,observation
                FROM dragon_evidence_passes
                WHERE owner=? AND source_id=? AND source_revision=? AND pass_id=?
            """, (owner, item.source_id, item.source_revision,
                  item.pass_id)).fetchone()
            current = (
                item.claim_id, int(item.supports), item.confidence,
                item.reliability, item.independence_group,
                item.evidence_locator, item.observation,
            )
            if existing:
                if existing != current:
                    raise ValueError("immutable evidence identity conflict")
                return
            count = self.db.execute("""
                SELECT COUNT(*) FROM dragon_evidence_passes
                WHERE owner=? AND claim_id=?
            """, (owner, item.claim_id)).fetchone()[0]
            if count >= self.distiller.policy.max_evidence:
                raise ValueError("evidence budget exceeded")
            source_count = self.db.execute("""
                SELECT COUNT(*) FROM dragon_evidence_passes
                WHERE owner=? AND source_id=? AND source_revision=?
            """, (owner, item.source_id, item.source_revision)).fetchone()[0]
            if source_count >= self.distiller.policy.max_passes_per_source:
                raise ValueError("reread budget exceeded")
            self.db.execute("""
                INSERT INTO dragon_evidence_passes VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """, (owner, item.claim_id, item.source_id, item.source_revision,
                  item.pass_id, int(item.supports), item.confidence,
                  item.reliability, item.independence_group,
                  item.evidence_locator, item.observation))

    def readings(self, owner: str, claim_id: str, *,
                 authorized: bool) -> tuple[EvidencePass, ...]:
        if not authorized:
            raise PermissionError("evidence reading requires authorization")
        rows = self.db.execute("""
            SELECT source_id,source_revision,pass_id,claim_id,supports,
                   confidence,reliability,independence_group,
                   evidence_locator,observation
            FROM dragon_evidence_passes
            WHERE owner=? AND claim_id=?
            ORDER BY source_id,source_revision,pass_id
        """, (owner, claim_id)).fetchall()
        return tuple(EvidencePass(
            row[0], row[1], row[2], row[3], bool(row[4]),
            row[5], row[6], row[7], row[8], row[9],
        ) for row in rows)

    def belief(self, owner: str, claim_id: str, *,
               authorized: bool) -> Belief:
        return self.distiller.distill(
            claim_id, self.readings(owner, claim_id, authorized=authorized),
        )

    def erase(self, owner: str, *, authorized: bool) -> int:
        if not authorized:
            raise PermissionError("evidence erasure requires authorization")
        with self.db:
            return self.db.execute(
                "DELETE FROM dragon_evidence_passes WHERE owner=?",
                (owner,),
            ).rowcount
