"""Deterministic, replayable audit ledger for Jeeves decisions.

The ledger is intentionally append-only in its public model.  A decision is
not merely a log line: it records the state observations, policy inputs,
evidence references, causal predecessors and resulting action.  Records carry
content hashes so a replay adapter can detect mutation or omission without
requiring a database or model provider.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from typing import Iterable, Mapping, Sequence


class EvidenceKind(str, Enum):
    OBSERVATION = "observation"
    ASSESSMENT = "assessment"
    MEMORY = "memory"
    KNOWLEDGE = "knowledge"
    REFLECTION = "reflection"
    TOOL = "tool"
    MODEL = "model"
    SYSTEM = "system"


class DecisionDisposition(str, Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    DEFERRED = "deferred"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    kind: EvidenceKind
    subject: str
    summary: str
    confidence: float = 1.0
    source_id: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("evidence confidence must be in [0, 1]")


@dataclass(frozen=True)
class DecisionRecord:
    sequence: int
    decision_id: str
    session_id: str
    domain: str
    action: str
    rationale: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    predecessors: tuple[str, ...] = ()
    state_digest: str = ""
    policy_digest: str = ""
    disposition: DecisionDisposition = DecisionDisposition.PROPOSED
    record_hash: str = ""


@dataclass(frozen=True)
class LedgerCheckpoint:
    sequence: int
    head_hash: str
    record_count: int


@dataclass
class DecisionLedger:
    """Append-only decision history with deterministic integrity checks."""

    records: list[DecisionRecord] = field(default_factory=list)
    evidence: dict[str, EvidenceRef] = field(default_factory=dict)
    _head_hash: str = "GENESIS"

    @property
    def head_hash(self) -> str:
        return self._head_hash

    def register_evidence(self, item: EvidenceRef) -> None:
        existing = self.evidence.get(item.evidence_id)
        if existing is not None and existing != item:
            raise ValueError(f"evidence id collision: {item.evidence_id}")
        self.evidence[item.evidence_id] = item

    def append(
        self,
        *,
        session_id: str,
        decision_id: str,
        domain: str,
        action: str,
        rationale: Sequence[str] = (),
        evidence: Sequence[str] = (),
        predecessors: Sequence[str] = (),
        state: Mapping[str, object] | None = None,
        policy: Mapping[str, object] | None = None,
        disposition: DecisionDisposition = DecisionDisposition.PROPOSED,
    ) -> DecisionRecord:
        if any(record.decision_id == decision_id for record in self.records):
            raise ValueError(f"duplicate decision id: {decision_id}")
        missing = tuple(item for item in evidence if item not in self.evidence)
        if missing:
            raise ValueError(f"unknown evidence references: {missing}")
        missing_predecessors = tuple(item for item in predecessors if not any(r.decision_id == item for r in self.records))
        if missing_predecessors:
            raise ValueError(f"unknown predecessor decisions: {missing_predecessors}")
        sequence = len(self.records) + 1
        state_digest = self._digest(state or {})
        policy_digest = self._digest(policy or {})
        unsigned = {
            "sequence": sequence,
            "decision_id": decision_id,
            "session_id": session_id,
            "domain": domain,
            "action": action,
            "rationale": tuple(rationale),
            "evidence": tuple(evidence),
            "predecessors": tuple(predecessors),
            "state_digest": state_digest,
            "policy_digest": policy_digest,
            "disposition": disposition.value,
            "previous": self._head_hash,
        }
        record_hash = self._digest(unsigned)
        record = DecisionRecord(sequence, decision_id, session_id, domain, action, tuple(rationale), tuple(evidence), tuple(predecessors), state_digest, policy_digest, disposition, record_hash)
        self.records.append(record)
        self._head_hash = record_hash
        return record

    def checkpoint(self) -> LedgerCheckpoint:
        return LedgerCheckpoint(len(self.records), self._head_hash, len(self.records))

    def verify(self) -> None:
        previous = "GENESIS"
        for expected_sequence, record in enumerate(self.records, 1):
            if record.sequence != expected_sequence:
                raise ValueError("decision sequence is not contiguous")
            payload = {
                "sequence": record.sequence,
                "decision_id": record.decision_id,
                "session_id": record.session_id,
                "domain": record.domain,
                "action": record.action,
                "rationale": record.rationale,
                "evidence": record.evidence,
                "predecessors": record.predecessors,
                "state_digest": record.state_digest,
                "policy_digest": record.policy_digest,
                "disposition": record.disposition.value,
                "previous": previous,
            }
            expected = self._digest(payload)
            if record.record_hash != expected:
                raise ValueError(f"decision hash mismatch at sequence {record.sequence}")
            previous = record.record_hash
        if previous != self._head_hash:
            raise ValueError("ledger head hash mismatch")

    def session(self, session_id: str) -> tuple[DecisionRecord, ...]:
        return tuple(record for record in self.records if record.session_id == session_id)

    def explain(self, decision_id: str) -> tuple[DecisionRecord, ...]:
        """Return the causal ancestry of a decision in deterministic order."""
        by_id = {record.decision_id: record for record in self.records}
        if decision_id not in by_id:
            raise KeyError(decision_id)
        seen: set[str] = set()
        ordered: list[DecisionRecord] = []

        def visit(current: str) -> None:
            if current in seen:
                return
            seen.add(current)
            record = by_id[current]
            for predecessor in record.predecessors:
                if predecessor in by_id:
                    visit(predecessor)
            ordered.append(record)

        visit(decision_id)
        return tuple(ordered)

    def supersede(self, decision_id: str, *, replacement_id: str) -> DecisionRecord:
        target = next((record for record in self.records if record.decision_id == decision_id), None)
        if target is None:
            raise KeyError(decision_id)
        if any(record.decision_id == replacement_id for record in self.records):
            raise ValueError(f"duplicate decision id: {replacement_id}")
        return self.append(
            session_id=target.session_id,
            decision_id=replacement_id,
            domain=target.domain,
            action=target.action,
            rationale=target.rationale + (f"supersedes:{decision_id}",),
            evidence=target.evidence,
            predecessors=(decision_id,),
            disposition=DecisionDisposition.ACCEPTED,
        )

    @staticmethod
    def _digest(value: object) -> str:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def evidence_bundle(items: Iterable[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    """Canonicalize an evidence collection while rejecting duplicate identities."""
    result: dict[str, EvidenceRef] = {}
    for item in items:
        if item.evidence_id in result and result[item.evidence_id] != item:
            raise ValueError(f"conflicting evidence: {item.evidence_id}")
        result[item.evidence_id] = item
    return tuple(result[key] for key in sorted(result))
