"""Logical-clock and causal-order contracts for VOL-299.

Wall-clock timestamps are deliberately absent from ordering decisions.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


_MAX_COUNTER = (1 << 63) - 1


@dataclass(frozen=True, order=True)
class SequenceNumber:
    value: int

    def __post_init__(self) -> None:
        if not isinstance(self.value, int) or isinstance(self.value, bool) or not 0 <= self.value <= _MAX_COUNTER:
            raise ValueError("sequence number must be an unsigned 63-bit integer")

    def next(self) -> "SequenceNumber":
        if self.value == _MAX_COUNTER:
            raise OverflowError("sequence number exhausted")
        return SequenceNumber(self.value + 1)


@dataclass(frozen=True)
class LogicalClock:
    node_id: str
    counter: SequenceNumber = SequenceNumber(0)

    def __post_init__(self) -> None:
        if not self.node_id or not self.node_id.isascii() or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in self.node_id):
            raise ValueError("node_id must be canonical lowercase ASCII")

    def tick(self) -> "LogicalClock":
        return LogicalClock(self.node_id, self.counter.next())

    def observe(self, remote: "LogicalClock") -> "LogicalClock":
        if self.counter.value == _MAX_COUNTER or remote.counter.value == _MAX_COUNTER:
            raise OverflowError("logical clock exhausted")
        return LogicalClock(self.node_id, SequenceNumber(max(self.counter.value, remote.counter.value) + 1))


class CausalRelation(str, Enum):
    BEFORE = "before"
    AFTER = "after"
    EQUAL = "equal"
    CONCURRENT = "concurrent"


@dataclass(frozen=True)
class VectorClock:
    entries: tuple[tuple[str, SequenceNumber], ...] = ()

    @classmethod
    def from_mapping(cls, values: Mapping[str, int]) -> "VectorClock":
        if any(not isinstance(k, str) or not k or not k.isascii() or k.lower() != k for k in values):
            raise ValueError("vector-clock node IDs must be canonical lowercase ASCII")
        return cls(tuple(sorted((k, SequenceNumber(v)) for k, v in values.items())))

    def as_mapping(self) -> dict[str, int]:
        return {node: seq.value for node, seq in self.entries}

    def relation(self, other: "VectorClock") -> CausalRelation:
        left, right = self.as_mapping(), other.as_mapping()
        nodes = set(left) | set(right)
        le = all(left.get(n, 0) <= right.get(n, 0) for n in nodes)
        ge = all(left.get(n, 0) >= right.get(n, 0) for n in nodes)
        if le and ge:
            return CausalRelation.EQUAL
        if le:
            return CausalRelation.BEFORE
        if ge:
            return CausalRelation.AFTER
        return CausalRelation.CONCURRENT

    def merge(self, other: "VectorClock") -> "VectorClock":
        left, right = self.as_mapping(), other.as_mapping()
        return VectorClock.from_mapping({n: max(left.get(n, 0), right.get(n, 0)) for n in set(left) | set(right)})


@dataclass(frozen=True, order=True)
class FencingToken:
    value: SequenceNumber

    def supersedes(self, other: "FencingToken") -> bool:
        return self.value.value > other.value.value
