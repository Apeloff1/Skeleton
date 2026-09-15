"""Causal graph layer for the Skeleton kernel — v16.2.

The event bus threads ``correlation_id`` and ``causation_id`` through every
event it publishes, but it never *assembles* them into anything. ``CausalGraph``
does the assembly: feed it a ``EventBus.trace`` slice (or stream events in as
they're published) and it builds the directed graph of cause → effect for a
whole pipeline run, swarm execution, or Jeeves session.

From the graph you get, for free:

- **roots** — events that started a causal chain (no causation event seen)
- **leaves** — events that caused nothing further (chain terminals)
- **lineage(event_id)** — the ordered chain of causes from root to the event
- **frontier()** — events with no successors yet: the "live edge" of the run
- **fan_out(node)** — how wide a single cause fanned the run out
- **cycles()** — causal loops, which indicate feedback (or a bug)

The graph is pure domain: no I/O, no framework imports, no clock reads of its
own — it trusts the timestamps already on the events.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator

from skeleton.kernel.errors import KernelError
from skeleton.kernel.events import DomainEvent


class CausalGraphError(KernelError):
    """Raised when a graph operation is ill-posed (unknown node, etc.)."""

    code = "KRN.CAUSAL_GRAPH"


@dataclass(frozen=True)
class CausalNode:
    """A single event's place in the causal graph."""

    event: DomainEvent
    parent_id: str | None          # causation_id, if the parent event is known
    child_ids: tuple[str, ...] = ()
    depth: int = 0                 # distance from the nearest root

    @property
    def is_root(self) -> bool:
        return self.parent_id is None

    @property
    def is_leaf(self) -> bool:
        return not self.child_ids


@dataclass(frozen=True)
class CausalPath:
    """An ordered chain of events from cause to effect."""

    event_ids: tuple[str, ...]
    topics: tuple[str, ...]
    correlation_id: str
    elapsed_seconds: float

    def __len__(self) -> int:
        return len(self.event_ids)


class CausalGraph:
    """Directed cause→effect graph over correlated domain events.

    Events are added exactly once (duplicates by ``event_id`` are ignored).
    Edges are resolved lazily: an event may name a ``causation_id`` whose
    parent has not yet been seen; the edge is grafted on when the parent
    arrives. Events whose parents never arrive are treated as roots.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, CausalNode] = {}
        self._children: dict[str, list[str]] = defaultdict(list)
        self._pending_parents: dict[str, list[str]] = defaultdict(list)
        self._correlations: set[str] = set()

    # -- ingestion ---------------------------------------------------------

    def add(self, event: DomainEvent) -> None:
        """Ingest one event. Idempotent on ``event_id``."""
        if event.event_id in self._nodes:
            return
        self._correlations.add(event.correlation_id)
        parent = event.causation_id
        if parent is not None and parent in self._nodes:
            self._children[parent].append(event.event_id)
        elif parent is not None:
            self._pending_parents[parent].append(event.event_id)
        self._nodes[event.event_id] = CausalNode(
            event=event,
            parent_id=parent if parent in self._nodes or parent is not None else None,
        )
        # graft any children that arrived before their parent
        for orphan in self._pending_parents.pop(event.event_id, []):
            self._children[event.event_id].append(orphan)

    def add_all(self, events: Iterable[DomainEvent]) -> int:
        """Ingest many events; returns how many were new."""
        before = len(self._nodes)
        for e in events:
            self.add(e)
        return len(self._nodes) - before

    @classmethod
    def from_bus(cls, bus: "Any", correlation_id: str | None = None) -> "CausalGraph":
        """Build a graph from an EventBus replay buffer.

        With ``correlation_id`` set, only that run's causal chain is graphed;
        otherwise every retained event is included.
        """
        graph = cls()
        events = bus.trace(correlation_id) if correlation_id else bus.replay("*")
        graph.add_all(events)
        return graph

    # -- queries -----------------------------------------------------------

    def node(self, event_id: str) -> CausalNode:
        try:
            base = self._nodes[event_id]
        except KeyError:
            raise CausalGraphError(
                f"Unknown event {event_id!r}",
                context={"event_id": event_id, "known": len(self._nodes)},
            )
        return CausalNode(
            event=base.event,
            parent_id=base.parent_id,
            child_ids=tuple(self._children.get(event_id, ())),
            depth=self._depth(event_id),
        )

    def roots(self) -> list[CausalNode]:
        """Events with no known causal parent — the origins of each chain."""
        return [self.node(eid) for eid, n in self._nodes.items() if n.parent_id is None]

    def leaves(self) -> list[CausalNode]:
        """Events that caused nothing further — chain terminals."""
        return [self.node(eid) for eid in self._nodes if not self._children.get(eid)]

    def frontier(self) -> list[CausalNode]:
        """Alias for leaves: the live edge of the run, useful while streaming."""
        return self.leaves()

    def children(self, event_id: str) -> list[CausalNode]:
        self._require(event_id)
        return [self.node(c) for c in self._children.get(event_id, ())]

    def lineage(self, event_id: str) -> CausalPath:
        """The ordered causal chain from the nearest root down to ``event_id``."""
        self._require(event_id)
        chain: list[str] = []
        current: str | None = event_id
        guard = 0
        while current is not None:
            chain.append(current)
            current = self._nodes[current].parent_id
            guard += 1
            if guard > len(self._nodes) + 1:  # pragma: no cover - cycle safety net
                raise CausalGraphError("Cycle detected while walking lineage",
                                       context={"event_id": event_id})
        chain.reverse()
        events = [self._nodes[e].event for e in chain]
        elapsed = events[-1].occurred_at - events[0].occurred_at if len(events) > 1 else 0.0
        return CausalPath(
            event_ids=tuple(chain),
            topics=tuple(e.topic for e in events),
            correlation_id=self._nodes[event_id].event.correlation_id,
            elapsed_seconds=elapsed,
        )

    def fan_out(self, event_id: str | None = None) -> dict[str, int] | int:
        """Direct child count for one node, or for the whole graph."""
        if event_id is not None:
            self._require(event_id)
            return len(self._children.get(event_id, ()))
        return {eid: len(kids) for eid, kids in self._children.items()}

    def cycles(self) -> list[list[str]]:
        """Detect causal loops. A healthy DAG returns an empty list."""
        found: list[list[str]] = []
        state: dict[str, int] = {}  # 0=unvisited 1=in-stack 2=done
        stack: list[str] = []

        def visit(eid: str) -> None:
            state[eid] = 1
            stack.append(eid)
            for child in self._children.get(eid, ()):
                if state.get(child, 0) == 1:
                    idx = stack.index(child)
                    found.append(stack[idx:] + [child])
                elif state.get(child, 0) == 0:
                    visit(child)
            stack.pop()
            state[eid] = 2

        for eid in self._nodes:
            if state.get(eid, 0) == 0:
                visit(eid)
        return found

    def stats(self) -> dict[str, Any]:
        """Shape summary of the graph."""
        depths = [self._depth(e) for e in self._nodes] if self._nodes else [0]
        return {
            "events": len(self._nodes),
            "edges": sum(len(c) for c in self._children.values()),
            "roots": sum(1 for n in self._nodes.values() if n.parent_id is None),
            "leaves": sum(1 for e in self._nodes if not self._children.get(e)),
            "max_depth": max(depths),
            "correlations": len(self._correlations),
            "cycles": len(self.cycles()),
        }

    # -- traversal ----------------------------------------------------------

    def walk(self, from_event_id: str | None = None) -> Iterator[CausalNode]:
        """Breadth-first traversal from a node, or from every root in order."""
        starts = [from_event_id] if from_event_id else [n.event.event_id for n in self.roots()]
        seen: set[str] = set()
        queue: list[str] = [s for s in starts if s is not None]
        while queue:
            eid = queue.pop(0)
            if eid in seen or eid not in self._nodes:
                continue
            seen.add(eid)
            yield self.node(eid)
            queue.extend(self._children.get(eid, ()))

    # -- internals -----------------------------------------------------------

    def _require(self, event_id: str) -> None:
        if event_id not in self._nodes:
            raise CausalGraphError(
                f"Unknown event {event_id!r}",
                context={"event_id": event_id, "known": len(self._nodes)},
            )

    def _depth(self, event_id: str) -> int:
        depth, current, guard = 0, self._nodes[event_id].parent_id, 0
        while current is not None and guard <= len(self._nodes):
            depth += 1
            current = self._nodes[current].parent_id
            guard += 1
        return depth


__all__ = [
    "CausalGraph",
    "CausalGraphError",
    "CausalNode",
    "CausalPath",
]
