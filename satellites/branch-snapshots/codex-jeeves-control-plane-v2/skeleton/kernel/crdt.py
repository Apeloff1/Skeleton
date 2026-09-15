"""CRDTs — conflict-free replicated data types for swarm-wide state.

When the mesh partitions, agents keep working; when it heals, state must
merge *without coordination* and every replica must converge to the same
value. CRDTs give exactly that: merge operations that are associative,
commutative, and idempotent, so gossip order and duplicates don't matter.

Provided types:

- :class:`GCounter` — grow-only counter (increments never lost).
- :class:`PNCounter` — counter with increment *and* decrement.
- :class:`LWWRegister` — last-writer-wins value cell; ties broken by
  node id for determinism.
- :class:`ORSet` — add/remove set with causal tags, so remove doesn't
  clobber a concurrent add (add-wins semantics).

All merges are total functions of the two states — no vector clocks
required by callers, no tombstone GC coordination.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Hashable, Optional, Set, Tuple

from .errors import KernelError


class CRDTError(KernelError):
    code = "KRN.CRDT"


# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------

class GCounter:
    """Grow-only counter: per-node counts, value = sum of all entries."""

    __slots__ = ("node_id", "_counts")

    def __init__(self, node_id: str, counts: Optional[Dict[str, int]] = None) -> None:
        if not node_id:
            raise CRDTError("GCounter requires a node id")
        self.node_id = node_id
        self._counts: Dict[str, int] = dict(counts or {})

    @property
    def value(self) -> int:
        return sum(self._counts.values())

    def increment(self, amount: int = 1) -> "GCounter":
        if amount < 0:
            raise CRDTError("GCounter cannot decrement — use PNCounter",
                            context={"amount": amount})
        self._counts[self.node_id] = self._counts.get(self.node_id, 0) + amount
        return self

    def merge(self, other: "GCounter") -> "GCounter":
        for node, count in other._counts.items():
            self._counts[node] = max(self._counts.get(node, 0), count)
        return self

    def state(self) -> Dict[str, int]:
        return dict(self._counts)

    @classmethod
    def from_state(cls, node_id: str, state: Dict[str, int]) -> "GCounter":
        return cls(node_id, state)


class PNCounter:
    """Increment/decrement counter built from two G-Counters."""

    __slots__ = ("_inc", "_dec")

    def __init__(self, node_id: str,
                 inc: Optional[Dict[str, int]] = None,
                 dec: Optional[Dict[str, int]] = None) -> None:
        self._inc = GCounter(node_id, inc)
        self._dec = GCounter(node_id, dec)

    @property
    def value(self) -> int:
        return self._inc.value - self._dec.value

    def increment(self, amount: int = 1) -> "PNCounter":
        self._inc.increment(amount)
        return self

    def decrement(self, amount: int = 1) -> "PNCounter":
        self._dec.increment(amount)
        return self

    def merge(self, other: "PNCounter") -> "PNCounter":
        self._inc.merge(other._inc)
        self._dec.merge(other._dec)
        return self

    def state(self) -> Dict[str, Dict[str, int]]:
        return {"inc": self._inc.state(), "dec": self._dec.state()}

    @classmethod
    def from_state(cls, node_id: str, state: Dict[str, Dict[str, int]]) -> "PNCounter":
        return cls(node_id, state.get("inc"), state.get("dec"))


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Stamp:
    clock: float
    node: str

    def beats(self, other: "_Stamp") -> bool:
        return (self.clock, self.node) > (other.clock, other.node)


class LWWRegister:
    """Last-writer-wins register; concurrent writes resolve deterministically."""

    __slots__ = ("node_id", "_value", "_stamp")

    def __init__(self, node_id: str, value: Any = None,
                 clock: float = 0.0) -> None:
        if not node_id:
            raise CRDTError("LWWRegister requires a node id")
        self.node_id = node_id
        self._value = value
        self._stamp = _Stamp(clock, node_id)

    @property
    def value(self) -> Any:
        return self._value

    def set(self, value: Any, clock: float) -> None:
        stamp = _Stamp(clock, self.node_id)
        if stamp.beats(self._stamp):
            self._value, self._stamp = value, stamp

    def merge(self, other: "LWWRegister") -> "LWWRegister":
        if other._stamp.beats(self._stamp):
            self._value, self._stamp = other._value, other._stamp
        return self

    def state(self) -> Dict[str, Any]:
        return {"value": self._value, "clock": self._stamp.clock, "node": self._stamp.node}


# ---------------------------------------------------------------------------
# OR-Set (add-wins)
# ---------------------------------------------------------------------------

class ORSet:
    """Observed-remove set: remove only deletes the tags the remover saw,
    so a concurrent add on another replica survives the merge."""

    __slots__ = ("node_id", "_adds", "_removes", "_seq")

    def __init__(self, node_id: str) -> None:
        if not node_id:
            raise CRDTError("ORSet requires a node id")
        self.node_id = node_id
        self._adds: Dict[Hashable, Set[Tuple[str, int]]] = {}
        self._removes: Dict[Hashable, Set[Tuple[str, int]]] = {}
        self._seq = 0

    def _fresh_tag(self) -> Tuple[str, int]:
        self._seq += 1
        return (self.node_id, self._seq)

    def add(self, element: Hashable) -> None:
        self._adds.setdefault(element, set()).add(self._fresh_tag())

    def remove(self, element: Hashable) -> None:
        seen = self._adds.get(element, set())
        if seen:
            self._removes.setdefault(element, set()).update(seen)

    def contains(self, element: Hashable) -> bool:
        return bool(self._adds.get(element, set()) - self._removes.get(element, set()))

    def elements(self) -> Set[Hashable]:
        return {e for e in self._adds if self.contains(e)}

    def merge(self, other: "ORSet") -> "ORSet":
        for e, tags in other._adds.items():
            self._adds.setdefault(e, set()).update(tags)
        for e, tags in other._removes.items():
            self._removes.setdefault(e, set()).update(tags)
        self._seq = max(self._seq,
                        max((t[1] for tags in self._adds.values() for t in tags
                             if t[0] == self.node_id), default=0))
        return self

    def state(self) -> Dict[str, Any]:
        return {
            "adds": {repr(e): sorted(tags) for e, tags in self._adds.items()},
            "removes": {repr(e): sorted(tags) for e, tags in self._removes.items()},
            "seq": self._seq,
        }

    def __len__(self) -> int:
        return len(self.elements())

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"ORSet({sorted(self.elements())!r})"
