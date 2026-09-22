"""Deterministic append-only, hash-chained decision ledger."""
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
        if not 0 <= self.confidence <= 1:
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
    supersedes: str | None = None
    record_hash: str = ""


@dataclass(frozen=True)
class LedgerCheckpoint:
    sequence: int
    head_hash: str
    record_count: int


@dataclass
class DecisionLedger:
    records: list[DecisionRecord] = field(default_factory=list)
    evidence: dict[str, EvidenceRef] = field(default_factory=dict)
    _head_hash: str = "GENESIS"

    @property
    def head_hash(self) -> str:
        return self._head_hash

    def register_evidence(self, item: EvidenceRef) -> None:
        old = self.evidence.get(item.evidence_id)
        if old is not None and old != item:
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
        supersedes: str | None = None,
    ) -> DecisionRecord:
        if any(r.decision_id == decision_id for r in self.records):
            raise ValueError(f"duplicate decision id: {decision_id}")
        if supersedes == decision_id:
            raise ValueError("a decision cannot supersede itself")
        missing = tuple(e for e in evidence if e not in self.evidence)
        if missing:
            raise ValueError(f"unknown evidence references: {missing}")
        by_id = {r.decision_id: r for r in self.records}
        missingp = tuple(p for p in predecessors if p not in by_id)
        if missingp:
            raise ValueError(f"unknown predecessor decisions: {missingp}")
        if any(by_id[p].sequence >= len(self.records) + 1 for p in predecessors):
            raise ValueError("predecessor decisions must precede the appended decision")
        if supersedes is not None and supersedes not in by_id:
            raise ValueError(f"unknown superseded decision: {supersedes}")
        if supersedes is not None:
            target = by_id[supersedes]
            if target.sequence >= len(self.records) + 1:
                raise ValueError("superseded decision must precede its replacement")
            if target.session_id != session_id:
                raise ValueError("superseded decision must belong to the same session")
            if disposition is not DecisionDisposition.ACCEPTED:
                raise ValueError("superseding replacement must be accepted")
            if tuple(predecessors) != (supersedes,):
                raise ValueError("supersession predecessor must name the superseded decision")
            if target.supersedes is not None or target.decision_id in self.superseded_ids():
                raise ValueError(f"decision already superseded: {supersedes}")
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
            "supersedes": supersedes,
            "previous": self._head_hash,
        }
        record_hash = self._digest(unsigned)
        record = DecisionRecord(
            sequence,
            decision_id,
            session_id,
            domain,
            action,
            tuple(rationale),
            tuple(evidence),
            tuple(predecessors),
            state_digest,
            policy_digest,
            disposition,
            supersedes,
            record_hash,
        )
        self.records.append(record)
        self._head_hash = record_hash
        return record

    def checkpoint(self) -> LedgerCheckpoint:
        return LedgerCheckpoint(len(self.records), self._head_hash, len(self.records))

    def verify(self) -> None:
        previous = "GENESIS"
        ids: set[str] = set()
        by_id: dict[str, DecisionRecord] = {}
        for expected, record in enumerate(self.records, 1):
            if record.sequence != expected:
                raise ValueError("decision sequence is not contiguous")
            if record.decision_id in ids:
                raise ValueError(f"duplicate decision id: {record.decision_id}")
            ids.add(record.decision_id)
            by_id[record.decision_id] = record
            for predecessor in record.predecessors:
                prior = by_id.get(predecessor)
                if prior is None:
                    raise ValueError(f"unknown predecessor decision: {predecessor}")
                if prior.sequence >= record.sequence:
                    raise ValueError(f"predecessor must precede decision: {record.decision_id}")
            if record.supersedes == record.decision_id:
                raise ValueError("decision cannot supersede itself")
            if record.supersedes is not None:
                prior = by_id.get(record.supersedes)
                if prior is None:
                    raise ValueError(f"superseded decision must precede replacement: {record.decision_id}")
                if prior.sequence >= record.sequence:
                    raise ValueError(f"superseded decision must precede replacement: {record.decision_id}")
                if prior.session_id != record.session_id:
                    raise ValueError(f"superseded decision must belong to the same session: {record.decision_id}")
                if record.disposition is not DecisionDisposition.ACCEPTED:
                    raise ValueError(f"superseding replacement must be accepted: {record.decision_id}")
                if record.predecessors != (record.supersedes,):
                    raise ValueError(f"supersession predecessor must name target: {record.decision_id}")
                if prior.supersedes is not None:
                    raise ValueError(f"supersession target is itself a replacement: {record.decision_id}")
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
                "supersedes": record.supersedes,
                "previous": previous,
            }
            expected_hash = self._digest(payload)
            if record.record_hash != expected_hash:
                raise ValueError(f"decision hash mismatch at sequence {record.sequence}")
            previous = record.record_hash
        if previous != self._head_hash:
            raise ValueError("ledger head hash mismatch")

    def session(self, session_id: str) -> tuple[DecisionRecord, ...]:
        return tuple(r for r in self.records if r.session_id == session_id)

    def superseded_ids(self) -> frozenset[str]:
        return frozenset(r.supersedes for r in self.records if r.supersedes is not None)

    def active_records(self, session_id: str | None = None) -> tuple[DecisionRecord, ...]:
        records = self.session(session_id) if session_id is not None else tuple(self.records)
        superseded = self.superseded_ids()
        return tuple(
            r
            for r in records
            if r.decision_id not in superseded and r.disposition is not DecisionDisposition.SUPERSEDED
        )

    def explain(self, decision_id: str) -> tuple[DecisionRecord, ...]:
        by = {r.decision_id: r for r in self.records}
        if decision_id not in by:
            raise KeyError(decision_id)
        seen: set[str] = set()
        ordered: list[DecisionRecord] = []

        def visit(current: str) -> None:
            if current in seen:
                return
            seen.add(current)
            record = by[current]
            for predecessor in record.predecessors:
                if predecessor in by:
                    visit(predecessor)
            if record.supersedes is not None and record.supersedes in by:
                visit(record.supersedes)
            ordered.append(record)

        visit(decision_id)
        return tuple(ordered)

    def supersede(self, decision_id: str, *, replacement_id: str) -> DecisionRecord:
        if decision_id == replacement_id:
            raise ValueError("a decision cannot supersede itself")
        if any(r.decision_id == replacement_id for r in self.records):
            raise ValueError(f"duplicate decision id: {replacement_id}")
        target = next((r for r in self.records if r.decision_id == decision_id), None)
        if target is None:
            raise KeyError(decision_id)
        if decision_id in self.superseded_ids():
            raise ValueError(f"decision already superseded: {decision_id}")
        return self.append(
            session_id=target.session_id,
            decision_id=replacement_id,
            domain=target.domain,
            action=target.action,
            rationale=target.rationale,
            evidence=target.evidence,
            predecessors=(decision_id,),
            state={"replacement_of": decision_id},
            policy={"replacement_of": decision_id},
            disposition=DecisionDisposition.ACCEPTED,
            supersedes=decision_id,
        )

    @staticmethod
    def _digest(value: object) -> str:
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()


def evidence_bundle(items: Iterable[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    result: dict[str, EvidenceRef] = {}
    for item in items:
        if item.evidence_id in result and result[item.evidence_id] != item:
            raise ValueError(f"conflicting evidence: {item.evidence_id}")
        result[item.evidence_id] = item
    return tuple(result[k] for k in sorted(result))
