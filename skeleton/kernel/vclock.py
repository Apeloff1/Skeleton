"""Vector clocks — causal ordering across the swarm without wall time.

Wall clocks lie: agents drift, NTP slews, containers freeze. A vector clock
orders events by *causation* instead of by timestamp. Each agent increments
its own counter on every local event and merges on message receipt; two
clocks are then comparable as happens-before, concurrent, or identical.

The event bus already threads correlation ids; vector clocks give the kernel
the missing primitive for *why* one event preceded another — which the
causality graph and the entanglement detector can both consume.

Pure domain: no I/O, no time source beyond what the caller supplies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Mapping, Optional

from skeleton.kernel.errors import KernelError


class ClockError(KernelError):
    code = "KRN.CLOCK"
    http_status = 400


class Ordering:
    BEFORE = "before"
    AFTER = "after"
    CONCURRENT = "concurrent"
    IDENTICAL = "identical"


@dataclass
class VectorClock:
    """A vector clock over string agent ids."""

    counters: Dict[str, int] = field(default_factory=dict)

    def tick(self, agent_id: str) -> "VectorClock":
        """Local event: increment own counter, return self for chaining."""
        if not agent_id:
            raise ClockError("tick() requires an agent id")
        self.counters[agent_id] = self.counters.get(agent_id, 0) + 1
        return self

    def merge(self, other: "VectorClock") -> "VectorClock":
        """Message receipt: elementwise max, then the caller ticks itself."""
        for agent, count in other.counters.items():
            self.counters[agent] = max(self.counters.get(agent, 0), count)
        return self

    def compare(self, other: "VectorClock") -> str:
        """The full four-way causal relation with another clock."""
        agents = set(self.counters) | set(other.counters)
        dominated = False
        dominates = False
        for agent in agents:
            a = self.counters.get(agent, 0)
            b = other.counters.get(agent, 0)
            if a < b:
                dominated = True
            elif a > b:
                dominates = True
        if dominated and dominates:
            return Ordering.CONCURRENT
        if dominated:
            return Ordering.BEFORE
        if dominates:
            return Ordering.AFTER
        return Ordering.IDENTICAL

    def happens_before(self, other: "VectorClock") -> bool:
        return self.compare(other) == Ordering.BEFORE

    def is_concurrent(self, other: "VectorClock") -> bool:
        return self.compare(other) == Ordering.CONCURRENT

    def copy(self) -> "VectorClock":
        return VectorClock(counters=dict(self.counters))

    def to_dict(self) -> Dict[str, int]:
        return dict(self.counters)

    @classmethod
    def from_dict(cls, data: Mapping[str, int]) -> "VectorClock":
        if not isinstance(data, Mapping):
            raise ClockError("VectorClock.from_dict requires a mapping")
        return cls(counters={str(k): int(v) for k, v in data.items()})
