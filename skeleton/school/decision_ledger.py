"""Deterministic append-only, hash-chained decision ledger.

Decision hashes bind not only evidence identifiers but the immutable content
identities of those evidence records.  The ledger also exposes an evidence root
and checkpoint identity so runtime replay can prove it observed the exact same
decision and evidence state.
"""
from __future__ import annotations

from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math
import threading
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


def _text(name: str, value: object, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    result = value.strip()
    if len(result) > maximum:
        raise ValueError(f"{name} exceeds {maximum} characters")
    return result


def _canonical(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("ledger payload contains non-finite number")
        return float(value)
    if isinstance(value, Enum):
        return _canonical(value.value)
    if isinstance(value, MappingABC):
        normalized: dict[str, object] = {}
        for raw_key, item in value.items():
            key = _text("ledger payload key", raw_key, maximum=256)
            if key in normalized:
                raise ValueError("ledger payload keys collide after normalization")
            normalized[key] = _canonical(item)
        return dict(sorted(normalized.items()))
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    raise ValueError(
        f"ledger payload contains unsupported type: {type(value).__name__}"
    )


def _digest(value: object) -> str:
    canonical = _canonical(value)
    try:
        payload = json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("ledger payload is not deterministic JSON") from exc
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sha(name: str, value: object, *, allow_genesis: bool = False) -> str:
    if allow_genesis and value == "GENESIS":
        return "GENESIS"
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise ValueError(f"{name} must be lowercase sha256")
    return value


def _unique_text(name: str, values: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(_text(name, value) for value in values)
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{name} values must be unique")
    return normalized


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    kind: EvidenceKind
    subject: str
    summary: str
    confidence: float = 1.0
    source_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _text("evidence_id", self.evidence_id))
        if not isinstance(self.kind, EvidenceKind):
            raise ValueError("evidence kind must be EvidenceKind")
        object.__setattr__(self, "subject", _text("evidence subject", self.subject))
        object.__setattr__(self, "summary", _text("evidence summary", self.summary))
        if (
            isinstance(self.confidence, bool)
            or not isinstance(self.confidence, (int, float))
            or not math.isfinite(float(self.confidence))
            or not 0.0 <= float(self.confidence) <= 1.0
        ):
            raise ValueError("evidence confidence must be finite and in [0, 1]")
        object.__setattr__(self, "confidence", float(self.confidence))
        if self.source_id:
            object.__setattr__(self, "source_id", _text("source_id", self.source_id))

    def as_dict(self) -> dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "kind": self.kind.value,
            "subject": self.subject,
            "summary": self.summary,
            "confidence": self.confidence,
            "source_id": self.source_id,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


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
    evidence_digests: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence <= 0
        ):
            raise ValueError("decision sequence must be positive integer")
        for field_name in ("decision_id", "session_id", "domain", "action"):
            object.__setattr__(
                self,
                field_name,
                _text(field_name, getattr(self, field_name)),
            )
        rationale = tuple(_text("rationale", item) for item in self.rationale)
        evidence = _unique_text("evidence", self.evidence)
        predecessors = _unique_text("predecessor", self.predecessors)
        object.__setattr__(self, "rationale", rationale)
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "predecessors", predecessors)
        if self.state_digest:
            object.__setattr__(self, "state_digest", _sha("state_digest", self.state_digest))
        if self.policy_digest:
            object.__setattr__(self, "policy_digest", _sha("policy_digest", self.policy_digest))
        if not isinstance(self.disposition, DecisionDisposition):
            raise ValueError("disposition must be DecisionDisposition")
        if self.supersedes is not None:
            object.__setattr__(
                self,
                "supersedes",
                _text("supersedes", self.supersedes),
            )
        if self.record_hash:
            object.__setattr__(
                self,
                "record_hash",
                _sha("record_hash", self.record_hash),
            )
        digests = tuple(_sha("evidence_digest", item) for item in self.evidence_digests)
        if digests and len(digests) != len(evidence):
            raise ValueError("evidence digest count must match evidence references")
        object.__setattr__(self, "evidence_digests", digests)

    def hash_payload(self, previous: str) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "decision_id": self.decision_id,
            "session_id": self.session_id,
            "domain": self.domain,
            "action": self.action,
            "rationale": list(self.rationale),
            "evidence": list(self.evidence),
            "evidence_digests": list(self.evidence_digests),
            "predecessors": list(self.predecessors),
            "state_digest": self.state_digest,
            "policy_digest": self.policy_digest,
            "disposition": self.disposition.value,
            "supersedes": self.supersedes,
            "previous": previous,
        }


@dataclass(frozen=True)
class LedgerCheckpoint:
    sequence: int
    head_hash: str
    record_count: int
    evidence_root: str = ""

    def __post_init__(self) -> None:
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 0
        ):
            raise ValueError("checkpoint sequence must be non-negative integer")
        if (
            isinstance(self.record_count, bool)
            or not isinstance(self.record_count, int)
            or self.record_count < 0
        ):
            raise ValueError("checkpoint record_count must be non-negative integer")
        if self.sequence != self.record_count:
            raise ValueError("checkpoint sequence and record_count must match")
        if self.head_hash:
            object.__setattr__(
                self,
                "head_hash",
                _sha("head_hash", self.head_hash, allow_genesis=True),
            )
        if self.evidence_root:
            object.__setattr__(
                self,
                "evidence_root",
                _sha("evidence_root", self.evidence_root),
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "head_hash": self.head_hash,
            "record_count": self.record_count,
            "evidence_root": self.evidence_root,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass
class DecisionLedger:
    records: list[DecisionRecord] = field(default_factory=list)
    evidence: dict[str, EvidenceRef] = field(default_factory=dict)
    _head_hash: str = "GENESIS"
    _lock: threading.RLock = field(
        default_factory=threading.RLock,
        repr=False,
        compare=False,
    )

    @property
    def head_hash(self) -> str:
        with self._lock:
            return self._head_hash

    @property
    def evidence_root(self) -> str:
        with self._lock:
            return _digest(
                {
                    "schema_version": "skeleton.decision_evidence_root.v1",
                    "evidence": [
                        [key, self.evidence[key].digest]
                        for key in sorted(self.evidence)
                    ],
                }
            )

    @property
    def ledger_identity(self) -> str:
        with self._lock:
            return _digest(
                {
                    "schema_version": "skeleton.decision_ledger_identity.v1",
                    "head_hash": self._head_hash,
                    "record_count": len(self.records),
                    "evidence_root": self.evidence_root,
                }
            )

    def register_evidence(self, item: EvidenceRef) -> None:
        if not isinstance(item, EvidenceRef):
            raise TypeError("item must be EvidenceRef")
        with self._lock:
            old = self.evidence.get(item.evidence_id)
            if old is not None and old != item:
                raise ValueError(
                    f"evidence id collision: {item.evidence_id}"
                )
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
        with self._lock:
            session_id = _text("session_id", session_id)
            decision_id = _text("decision_id", decision_id)
            domain = _text("domain", domain)
            action = _text("action", action)
            rationale_values = tuple(
                _text("rationale", item)
                for item in rationale
            )
            evidence_values = _unique_text("evidence", tuple(evidence))
            predecessor_values = _unique_text(
                "predecessor",
                tuple(predecessors),
            )
            if not isinstance(disposition, DecisionDisposition):
                raise ValueError("disposition must be DecisionDisposition")
            if any(r.decision_id == decision_id for r in self.records):
                raise ValueError(
                    f"duplicate decision id: {decision_id}"
                )
            if supersedes == decision_id:
                raise ValueError("a decision cannot supersede itself")

            missing = tuple(
                item
                for item in evidence_values
                if item not in self.evidence
            )
            if missing:
                raise ValueError(
                    f"unknown evidence references: {missing}"
                )
            evidence_digests = tuple(
                self.evidence[item].digest
                for item in evidence_values
            )
            by_id = {
                record.decision_id: record
                for record in self.records
            }
            missingp = tuple(
                item
                for item in predecessor_values
                if item not in by_id
            )
            if missingp:
                raise ValueError(
                    f"unknown predecessor decisions: {missingp}"
                )
            if any(
                by_id[item].sequence >= len(self.records) + 1
                for item in predecessor_values
            ):
                raise ValueError(
                    "predecessor decisions must precede the appended decision"
                )

            normalized_supersedes = (
                None
                if supersedes is None
                else _text("supersedes", supersedes)
            )
            if (
                normalized_supersedes is not None
                and normalized_supersedes not in by_id
            ):
                raise ValueError(
                    f"unknown superseded decision: {normalized_supersedes}"
                )
            if normalized_supersedes is not None:
                target = by_id[normalized_supersedes]
                if target.sequence >= len(self.records) + 1:
                    raise ValueError(
                        "superseded decision must precede its replacement"
                    )
                if target.session_id != session_id:
                    raise ValueError(
                        "superseded decision must belong to the same session"
                    )
                if disposition is not DecisionDisposition.ACCEPTED:
                    raise ValueError(
                        "superseding replacement must be accepted"
                    )
                if predecessor_values != (normalized_supersedes,):
                    raise ValueError(
                        "supersession predecessor must name the superseded decision"
                    )
                if (
                    target.supersedes is not None
                    or target.decision_id in self.superseded_ids()
                ):
                    raise ValueError(
                        f"decision already superseded: {normalized_supersedes}"
                    )

            sequence = len(self.records) + 1
            state_digest = _digest(state or {})
            policy_digest = _digest(policy or {})
            unsigned = {
                "sequence": sequence,
                "decision_id": decision_id,
                "session_id": session_id,
                "domain": domain,
                "action": action,
                "rationale": list(rationale_values),
                "evidence": list(evidence_values),
                "evidence_digests": list(evidence_digests),
                "predecessors": list(predecessor_values),
                "state_digest": state_digest,
                "policy_digest": policy_digest,
                "disposition": disposition.value,
                "supersedes": normalized_supersedes,
                "previous": self._head_hash,
            }
            record_hash = _digest(unsigned)
            record = DecisionRecord(
                sequence=sequence,
                decision_id=decision_id,
                session_id=session_id,
                domain=domain,
                action=action,
                rationale=rationale_values,
                evidence=evidence_values,
                predecessors=predecessor_values,
                state_digest=state_digest,
                policy_digest=policy_digest,
                disposition=disposition,
                supersedes=normalized_supersedes,
                record_hash=record_hash,
                evidence_digests=evidence_digests,
            )
            self.records.append(record)
            self._head_hash = record_hash
            return record

    def checkpoint(self) -> LedgerCheckpoint:
        with self._lock:
            return LedgerCheckpoint(
                len(self.records),
                self._head_hash,
                len(self.records),
                self.evidence_root,
            )

    def verify_checkpoint(self, checkpoint: LedgerCheckpoint) -> bool:
        if not isinstance(checkpoint, LedgerCheckpoint):
            raise TypeError("checkpoint must be LedgerCheckpoint")
        with self._lock:
            return checkpoint == self.checkpoint()

    def verify(self) -> None:
        with self._lock:
            previous = "GENESIS"
            ids: set[str] = set()
            by_id: dict[str, DecisionRecord] = {}
            for expected, record in enumerate(self.records, 1):
                if not isinstance(record, DecisionRecord):
                    raise ValueError(
                        f"invalid decision record at sequence {expected}"
                    )
                if record.sequence != expected:
                    raise ValueError(
                        "decision sequence is not contiguous"
                    )
                if record.decision_id in ids:
                    raise ValueError(
                        f"duplicate decision id: {record.decision_id}"
                    )
                ids.add(record.decision_id)
                by_id[record.decision_id] = record

                if len(record.evidence) != len(record.evidence_digests):
                    raise ValueError(
                        f"evidence digest count mismatch: {record.decision_id}"
                    )
                for evidence_id, evidence_digest in zip(
                    record.evidence,
                    record.evidence_digests,
                    strict=True,
                ):
                    item = self.evidence.get(evidence_id)
                    if item is None:
                        raise ValueError(
                            f"unknown evidence reference: {evidence_id}"
                        )
                    if item.digest != evidence_digest:
                        raise ValueError(
                            f"evidence content drift: {evidence_id}"
                        )

                for predecessor in record.predecessors:
                    prior = by_id.get(predecessor)
                    if prior is None:
                        raise ValueError(
                            f"unknown predecessor decision: {predecessor}"
                        )
                    if prior.sequence >= record.sequence:
                        raise ValueError(
                            f"predecessor must precede decision: {record.decision_id}"
                        )

                if record.supersedes == record.decision_id:
                    raise ValueError(
                        "decision cannot supersede itself"
                    )
                if record.supersedes is not None:
                    prior = by_id.get(record.supersedes)
                    if prior is None:
                        raise ValueError(
                            f"superseded decision must precede replacement: {record.decision_id}"
                        )
                    if prior.sequence >= record.sequence:
                        raise ValueError(
                            f"superseded decision must precede replacement: {record.decision_id}"
                        )
                    if prior.session_id != record.session_id:
                        raise ValueError(
                            f"superseded decision must belong to the same session: {record.decision_id}"
                        )
                    if record.disposition is not DecisionDisposition.ACCEPTED:
                        raise ValueError(
                            f"superseding replacement must be accepted: {record.decision_id}"
                        )
                    if record.predecessors != (record.supersedes,):
                        raise ValueError(
                            f"supersession predecessor must name target: {record.decision_id}"
                        )
                    if prior.supersedes is not None:
                        raise ValueError(
                            f"supersession target is itself a replacement: {record.decision_id}"
                        )

                expected_hash = _digest(
                    record.hash_payload(previous)
                )
                if record.record_hash != expected_hash:
                    raise ValueError(
                        f"decision hash mismatch at sequence {record.sequence}"
                    )
                previous = record.record_hash

            if previous != self._head_hash:
                raise ValueError("ledger head hash mismatch")

    def session(
        self,
        session_id: str,
    ) -> tuple[DecisionRecord, ...]:
        normalized = _text("session_id", session_id)
        with self._lock:
            return tuple(
                record
                for record in self.records
                if record.session_id == normalized
            )

    def superseded_ids(self) -> frozenset[str]:
        with self._lock:
            return frozenset(
                record.supersedes
                for record in self.records
                if record.supersedes is not None
            )

    def active_records(
        self,
        session_id: str | None = None,
    ) -> tuple[DecisionRecord, ...]:
        with self._lock:
            records = (
                self.session(session_id)
                if session_id is not None
                else tuple(self.records)
            )
            superseded = self.superseded_ids()
            return tuple(
                record
                for record in records
                if (
                    record.decision_id not in superseded
                    and record.disposition
                    is not DecisionDisposition.SUPERSEDED
                )
            )

    def explain(
        self,
        decision_id: str,
    ) -> tuple[DecisionRecord, ...]:
        normalized = _text("decision_id", decision_id)
        with self._lock:
            by = {
                record.decision_id: record
                for record in self.records
            }
            if normalized not in by:
                raise KeyError(normalized)
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
                if (
                    record.supersedes is not None
                    and record.supersedes in by
                ):
                    visit(record.supersedes)
                ordered.append(record)

            visit(normalized)
            return tuple(ordered)

    def supersede(
        self,
        decision_id: str,
        *,
        replacement_id: str,
    ) -> DecisionRecord:
        normalized = _text("decision_id", decision_id)
        replacement = _text("replacement_id", replacement_id)
        with self._lock:
            if normalized == replacement:
                raise ValueError(
                    "a decision cannot supersede itself"
                )
            if any(
                record.decision_id == replacement
                for record in self.records
            ):
                raise ValueError(
                    f"duplicate decision id: {replacement}"
                )
            target = next(
                (
                    record
                    for record in self.records
                    if record.decision_id == normalized
                ),
                None,
            )
            if target is None:
                raise KeyError(normalized)
            if normalized in self.superseded_ids():
                raise ValueError(
                    f"decision already superseded: {normalized}"
                )
            return self.append(
                session_id=target.session_id,
                decision_id=replacement,
                domain=target.domain,
                action=target.action,
                rationale=target.rationale,
                evidence=target.evidence,
                predecessors=(normalized,),
                state={"replacement_of": normalized},
                policy={"replacement_of": normalized},
                disposition=DecisionDisposition.ACCEPTED,
                supersedes=normalized,
            )

    @staticmethod
    def _digest(value: object) -> str:
        return _digest(value)


def evidence_bundle(
    items: Iterable[EvidenceRef],
) -> tuple[EvidenceRef, ...]:
    result: dict[str, EvidenceRef] = {}
    for item in items:
        if not isinstance(item, EvidenceRef):
            raise TypeError("items must contain EvidenceRef values")
        if (
            item.evidence_id in result
            and result[item.evidence_id] != item
        ):
            raise ValueError(
                f"conflicting evidence: {item.evidence_id}"
            )
        result[item.evidence_id] = item
    return tuple(result[key] for key in sorted(result))


__all__ = [
    "DecisionDisposition",
    "DecisionLedger",
    "DecisionRecord",
    "EvidenceKind",
    "EvidenceRef",
    "LedgerCheckpoint",
    "evidence_bundle",
]
