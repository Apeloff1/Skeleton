"""Bounded evaluation/evidence records for Jeeves.

Evaluation is evidence, not execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from ._canonical import bounded_text, canonical_digest, frozen_mapping

MAX_TEXT = 8192
MAX_CASES = 4096
MAX_EVIDENCE = 256
MAX_PAYLOAD_BYTES = 64 * 1024


class EvalState(str, Enum):
    NEW = "new"
    READY = "ready"
    RUNNING = "running"
    BLOCKED = "blocked"
    DONE = "done"
    FAILED = "failed"


def _finite_score(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"invalid {name}")
    value = float(value)
    if value != value or value in (float("inf"), float("-inf")) or not 0.0 <= value <= 1.0:
        raise ValueError(f"invalid {name}")
    return value


def _digest(value: Any) -> str:
    return canonical_digest(value, max_bytes=MAX_PAYLOAD_BYTES)


@dataclass(frozen=True)
class EvalRecord:
    name: str
    state: EvalState = EvalState.NEW
    payload: Mapping[str, Any] = field(default_factory=dict)
    evidence: tuple[str, ...] = ()
    score: float | None = None
    threshold: float | None = None
    suite: str = "default"

    def __post_init__(self) -> None:
        bounded_text(self.name, "eval name")
        bounded_text(self.suite, "suite")
        if not isinstance(self.state, EvalState):
            raise ValueError("invalid eval state")
        if not isinstance(self.evidence, tuple) or len(self.evidence) > MAX_EVIDENCE:
            raise ValueError("invalid evidence")
        object.__setattr__(self, "evidence", tuple(bounded_text(x, "evidence") for x in self.evidence))
        object.__setattr__(self, "payload", frozen_mapping(self.payload, max_bytes=MAX_PAYLOAD_BYTES))
        if (self.score is None) != (self.threshold is None):
            raise ValueError("score and threshold must be supplied together")
        if self.score is not None:
            object.__setattr__(self, "score", _finite_score(self.score, "score"))
            object.__setattr__(self, "threshold", _finite_score(self.threshold, "threshold"))
            if self.state not in (EvalState.DONE, EvalState.FAILED):
                raise ValueError("scored evaluation must be terminal")

    @property
    def passed(self) -> bool | None:
        if self.score is None:
            return None
        return self.state is EvalState.DONE and self.score >= self.threshold

    @property
    def digest(self) -> str:
        return _digest({
            "evidence": self.evidence,
            "name": self.name,
            "payload": dict(self.payload),
            "score": self.score,
            "state": self.state.value,
            "suite": self.suite,
            "threshold": self.threshold,
            "v": 1,
        })


@dataclass(frozen=True)
class EvalLedger:
    records: tuple[EvalRecord, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.records, tuple) or len(self.records) > MAX_CASES:
            raise ValueError("invalid eval records")
        identities: set[tuple[str, str]] = set()
        for record in self.records:
            if not isinstance(record, EvalRecord):
                raise ValueError("invalid eval record")
            identity = (record.suite, record.name)
            if identity in identities:
                raise ValueError("duplicate evaluation")
            identities.add(identity)

    def append(self, record: EvalRecord) -> "EvalLedger":
        if not isinstance(record, EvalRecord):
            raise ValueError("invalid eval record")
        return EvalLedger(self.records + (record,))

    @property
    def digest(self) -> str:
        return _digest({"records": [record.digest for record in self.records], "v": 1})

    def summary(self) -> Mapping[str, int]:
        passed = sum(record.passed is True for record in self.records)
        failed = sum(record.passed is False for record in self.records)
        pending = len(self.records) - passed - failed
        return MappingProxyType({"passed": passed, "failed": failed, "pending": pending})


def validate_eval(records: Sequence[EvalRecord]) -> tuple[str, ...]:
    if isinstance(records, (str, bytes)):
        raise ValueError("records must be a sequence")
    ledger = EvalLedger(tuple(records))
    return tuple(record.digest for record in ledger.records)
