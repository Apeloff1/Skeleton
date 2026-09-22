"""Vector clocks — causality tracking for the Skeleton event fabric.

Each agent (or any event-emitting entity) carries a :class:`VectorClock`:
a mapping of ``node_id -> logical counter``. Clocks support the standard
trio of operations — ``tick`` (local event), ``merge`` (receive a remote
clock), and comparison via :meth:`happens_before` /
:meth:`is_concurrent_with` — letting the kernel order events on the bus
by *causality* rather than wall-clock time, which is meaningless across
a distributed swarm with skewed clocks.

Zero dependencies, immutable-on-write (operations return new clocks),
and safe to serialise straight into event envelopes.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

from .errors import KernelError


class ClockError(KernelError):
    code = "KRN.CLOCK"


class VectorClock:
    """Immutable vector clock for one node's view of causal history."""

    __slots__ = ("_entries",)

    def __init__(self, entries: Optional[Mapping[str, int]] = None) -> None:
        clean: Dict[str, int] = {}
        for node, counter in (entries or {}).items():
            if not isinstance(node, str) or not node:
                raise ClockError(
                    "vector-clock node ids must be non-empty strings",
                    context={"node": repr(node)},
                )
            if not isinstance(counter, int) or counter < 0:
                raise ClockError(
                    "vector-clock counters must be non-negative integers",
                    context={"node": node, "counter": repr(counter)},
                )
            if counter:
                clean[node] = counter
        self._entries: Dict[str, int] = clean

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def tick(self, node_id: str, *, amount: int = 1) -> "VectorClock":
        """Record a local event at ``node_id``; returns a new clock."""
        if amount < 1:
            raise ClockError("tick amount must be >= 1", context={"amount": amount})
        entries = dict(self._entries)
        entries[node_id] = entries.get(node_id, 0) + amount
        return VectorClock(entries)

    def merge(self, other: "VectorClock") -> "VectorClock":
        """Element-wise maximum — the receive rule for message passing."""
        if not isinstance(other, VectorClock):
            raise ClockError(
                "can only merge with another VectorClock",
                context={"other": type(other).__name__},
            )
        nodes = set(self._entries) | set(other._entries)
        return VectorClock({
            n: max(self._entries.get(n, 0), other._entries.get(n, 0))
            for n in nodes
        })

    # ------------------------------------------------------------------
    # Causal comparison
    # ------------------------------------------------------------------

    def dominates(self, other: "VectorClock") -> bool:
        """True iff self >= other on every component (not necessarily strict)."""
        return all(
            self._entries.get(n, 0) >= c for n, c in other._entries.items()
        )

    def happens_before(self, other: "VectorClock") -> bool:
        """True iff self → other: self <= other everywhere, strict somewhere."""
        return self.dominates(other) is False and other.dominates(self) and self != other

    def is_concurrent_with(self, other: "VectorClock") -> bool:
        """True iff neither clock happens-before the other."""
        return not self.dominates(other) and not other.dominates(self)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get(self, node_id: str) -> int:
        return self._entries.get(node_id, 0)

    @property
    def nodes(self) -> Tuple[str, ...]:
        return tuple(sorted(self._entries))

    @property
    def lamport_sum(self) -> int:
        """Total event count — a weak scalar ordering, ties broken arbitrarily."""
        return sum(self._entries.values())

    def to_dict(self) -> Dict[str, int]:
        return dict(self._entries)

    @classmethod
    def from_dict(cls, data: Mapping[str, int]) -> "VectorClock":
        return cls(data)

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, VectorClock) and self._entries == other._entries

    def __lt__(self, other: "VectorClock") -> bool:
        return self.happens_before(other)

    def __le__(self, other: "VectorClock") -> bool:
        return other.dominates(self)

    def __hash__(self) -> int:
        return hash(tuple(sorted(self._entries.items())))

    def __repr__(self) -> str:
        return f"VectorClock({self._entries!r})"


class ClockRegistry:
    """Per-node clock bookkeeping for the kernel — one clock per agent."""

    def __init__(self) -> None:
        self._clocks: Dict[str, VectorClock] = {}

    def tick(self, node_id: str) -> VectorClock:
        clock = self._clocks.get(node_id, VectorClock()).tick(node_id)
        self._clocks[node_id] = clock
        return clock

    def receive(self, node_id: str, remote: VectorClock) -> VectorClock:
        """Merge an inbound clock, then tick locally (message-receive rule)."""
        merged = self._clocks.get(node_id, VectorClock()).merge(remote).tick(node_id)
        self._clocks[node_id] = merged
        return merged

    def snapshot(self, node_id: str) -> VectorClock:
        return self._clocks.get(node_id, VectorClock())

    def nodes(self) -> Iterable[str]:
        return tuple(sorted(self._clocks))

    def reset(self, node_id: Optional[str] = None) -> None:
        if node_id is None:
            self._clocks.clear()
        else:
            self._clocks.pop(node_id, None)


def order_events(
    events: Iterable[Tuple[str, VectorClock]],
) -> Tuple[Tuple[str, VectorClock], ...]:
    """Stable topological sort of (event_id, clock) pairs by causality.

    Concurrent events fall back to (lamport_sum, event_id) so the output
    is deterministic even when no causal order exists.
    """
    items = sorted(events, key=lambda kv: (kv[1].lamport_sum, kv[0]))
    ordered: list = []
    for item in items:
        inserted = False
        for i in range(len(ordered) - 1, -1, -1):
            if ordered[i][1].happens_before(item[1]) or ordered[i][1] == item[1]:
                ordered.insert(i + 1, item)
                inserted = True
                break
            if item[1].happens_before(ordered[i][1]):
                continue
        if not inserted:
            ordered.insert(0, item)
    return tuple(ordered)
