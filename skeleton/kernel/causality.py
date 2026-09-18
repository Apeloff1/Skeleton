"""Causal graph assembly for correlated Skeleton kernel events.

The graph is pure domain logic: it performs no I/O and reads no clock. It
reconstructs cause -> effect chains from ``DomainEvent`` identity, correlation
and causation metadata retained by ``EventBus``.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Iterable, Iterator

from skeleton.kernel.errors import KernelError
from skeleton.kernel.events import DomainEvent


class CausalGraphError(KernelError):
    """Raised when a causal graph query cannot be satisfied."""

    code = "KRN.CAUSAL_GRAPH"


@dataclass(frozen=True)
class CausalNode:
    event: DomainEvent
    parent_id: str | None
    child_ids: tuple[str, ...] = ()
    depth: int = 0

    @property
    def is_root(self) -> bool:
        return self.parent_id is None

    @property
    def is_leaf(self) -> bool:
        return not self.child_ids


@dataclass(frozen=True)
class CausalPath:
    event_ids: tuple[str, ...]
    topics: tuple[str, ...]
    correlation_id: str
    elapsed_seconds: float

    def __len__(self) -> int:
        return len(self.event_ids)


class CausalGraph:
    """Directed cause -> effect graph over correlated domain events.

    Ingestion is idempotent and accepts out-of-order streams. Children whose
    parents are outside the retained replay window are safely treated as roots;
    if the parent later arrives, the edge is grafted automatically.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, CausalNode] = {}
        self._children: dict[str, list[str]] = defaultdict(list)
        self._pending_parents: dict[str, list[str]] = defaultdict(list)
        self._correlations: set[str] = set()

    def add(self, event: DomainEvent) -> None:
        if event.event_id in self._nodes:
            return

        self._correlations.add(event.correlation_id)
        parent_id = event.causation_id
        self._nodes[event.event_id] = CausalNode(event=event, parent_id=parent_id)

        if parent_id is not None:
            if parent_id in self._nodes:
                self._link(parent_id, event.event_id)
            else:
                self._pending_parents[parent_id].append(event.event_id)

        for child_id in self._pending_parents.pop(event.event_id, ()):
            self._link(event.event_id, child_id)

    def add_all(self, events: Iterable[DomainEvent]) -> int:
        before = len(self._nodes)
        for event in events:
            self.add(event)
        return len(self._nodes) - before

    @classmethod
    def from_bus(cls, bus: Any, correlation_id: str | None = None) -> "CausalGraph":
        graph = cls()
        events = bus.trace(correlation_id) if correlation_id is not None else bus.replay("*")
        graph.add_all(events)
        return graph

    def node(self, event_id: str) -> CausalNode:
        self._require(event_id)
        base = self._nodes[event_id]
        return CausalNode(
            event=base.event,
            parent_id=self._resolved_parent_id(event_id),
            child_ids=tuple(self._children.get(event_id, ())),
            depth=self._depth(event_id),
        )

    def roots(self) -> list[CausalNode]:
        return [
            self.node(event_id)
            for event_id in self._nodes
            if self._resolved_parent_id(event_id) is None
        ]

    def leaves(self) -> list[CausalNode]:
        return [self.node(event_id) for event_id in self._nodes if not self._children.get(event_id)]

    def frontier(self) -> list[CausalNode]:
        return self.leaves()

    def children(self, event_id: str) -> list[CausalNode]:
        self._require(event_id)
        return [self.node(child_id) for child_id in self._children.get(event_id, ())]

    def lineage(self, event_id: str) -> CausalPath:
        self._require(event_id)
        chain: list[str] = []
        current: str | None = event_id
        seen: set[str] = set()

        while current is not None and current in self._nodes:
            if current in seen:
                raise CausalGraphError(
                    "Cycle detected while walking lineage",
                    context={"event_id": event_id, "cycle_at": current},
                )
            seen.add(current)
            chain.append(current)
            current = self._resolved_parent_id(current)

        chain.reverse()
        events = [self._nodes[item].event for item in chain]
        elapsed = events[-1].timestamp - events[0].timestamp if len(events) > 1 else 0.0
        return CausalPath(
            event_ids=tuple(chain),
            topics=tuple(event.topic for event in events),
            correlation_id=self._nodes[event_id].event.correlation_id,
            elapsed_seconds=max(0.0, elapsed),
        )

    def fan_out(self, event_id: str | None = None) -> dict[str, int] | int:
        if event_id is not None:
            self._require(event_id)
            return len(self._children.get(event_id, ()))
        return {item: len(self._children.get(item, ())) for item in self._nodes}

    def cycles(self) -> list[list[str]]:
        found: list[list[str]] = []
        state: dict[str, int] = {}
        stack: list[str] = []
        positions: dict[str, int] = {}

        def visit(event_id: str) -> None:
            state[event_id] = 1
            positions[event_id] = len(stack)
            stack.append(event_id)
            for child_id in self._children.get(event_id, ()):
                child_state = state.get(child_id, 0)
                if child_state == 1:
                    start = positions[child_id]
                    found.append(stack[start:] + [child_id])
                elif child_state == 0:
                    visit(child_id)
            stack.pop()
            positions.pop(event_id, None)
            state[event_id] = 2

        for event_id in self._nodes:
            if state.get(event_id, 0) == 0:
                visit(event_id)
        return found

    def stats(self) -> dict[str, int]:
        depths = [self._depth(event_id) for event_id in self._nodes] if self._nodes else [0]
        return {
            "events": len(self._nodes),
            "edges": sum(len(children) for children in self._children.values()),
            "roots": sum(
                1 for event_id in self._nodes if self._resolved_parent_id(event_id) is None
            ),
            "leaves": sum(1 for event_id in self._nodes if not self._children.get(event_id)),
            "max_depth": max(depths),
            "correlations": len(self._correlations),
            "cycles": len(self.cycles()),
        }

    def walk(self, from_event_id: str | None = None) -> Iterator[CausalNode]:
        if from_event_id is not None:
            self._require(from_event_id)
            starts = [from_event_id]
        else:
            starts = [node.event.event_id for node in self.roots()]

        queue = deque(starts)
        seen: set[str] = set()
        while queue:
            event_id = queue.popleft()
            if event_id in seen or event_id not in self._nodes:
                continue
            seen.add(event_id)
            yield self.node(event_id)
            queue.extend(self._children.get(event_id, ()))

    def _link(self, parent_id: str, child_id: str) -> None:
        children = self._children[parent_id]
        if child_id not in children:
            children.append(child_id)

    def _resolved_parent_id(self, event_id: str) -> str | None:
        parent_id = self._nodes[event_id].parent_id
        return parent_id if parent_id in self._nodes else None

    def _require(self, event_id: str) -> None:
        if event_id not in self._nodes:
            raise CausalGraphError(
                f"Unknown event {event_id!r}",
                context={"event_id": event_id, "known": len(self._nodes)},
            )

    def _depth(self, event_id: str) -> int:
        depth = 0
        current = event_id
        seen: set[str] = set()
        while current in self._nodes:
            if current in seen:
                return depth
            seen.add(current)
            parent_id = self._resolved_parent_id(current)
            if parent_id is None:
                return depth
            depth += 1
            current = parent_id
        return depth


__all__ = ["CausalGraph", "CausalGraphError", "CausalNode", "CausalPath"]
