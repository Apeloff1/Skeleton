"""Renderer-neutral world-agent navigation and schedule runtime.

Mined from Newmove2 NPC pathing semantics, but generalized for any generated
world. The runtime owns graph traversal, scheduled activities and contextual
schedule overrides without depending on React, coordinates in pixels, or a DB.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True, slots=True)
class WorldNode:
    id: str
    x: float
    y: float
    kind: str = "path"
    connections: tuple[str, ...] = ()


class NavigationError(ValueError):
    pass


class NavigationGraph:
    def __init__(self, nodes: Iterable[WorldNode]) -> None:
        self._nodes = {node.id: node for node in nodes}
        if not self._nodes:
            raise NavigationError("navigation graph cannot be empty")
        for node in self._nodes.values():
            for neighbor in node.connections:
                if neighbor not in self._nodes:
                    raise NavigationError(f"unknown connection {neighbor!r} from {node.id!r}")

    def node(self, node_id: str) -> WorldNode:
        try:
            return self._nodes[node_id]
        except KeyError as exc:
            raise NavigationError(f"unknown node: {node_id}") from exc

    def shortest_path(self, start: str, goal: str) -> tuple[str, ...]:
        self.node(start)
        self.node(goal)
        if start == goal:
            return (start,)
        queue: deque[str] = deque([start])
        previous: dict[str, str | None] = {start: None}
        while queue:
            current = queue.popleft()
            for neighbor in self._nodes[current].connections:
                if neighbor in previous:
                    continue
                previous[neighbor] = current
                if neighbor == goal:
                    path = [goal]
                    cursor: str | None = goal
                    while cursor is not None and cursor != start:
                        cursor = previous[cursor]
                        if cursor is not None:
                            path.append(cursor)
                    return tuple(reversed(path))
                queue.append(neighbor)
        raise NavigationError(f"no route from {start!r} to {goal!r}")


@dataclass(frozen=True, slots=True)
class ScheduleEntry:
    minute: int
    action: str
    location: str
    duration: int = 0
    interruptible: bool = True

    def __post_init__(self) -> None:
        if not 0 <= self.minute < 24 * 60:
            raise ValueError("minute must be within one day")
        if self.duration < 0:
            raise ValueError("duration cannot be negative")
        if not self.action or not self.location:
            raise ValueError("action and location are required")


@dataclass(frozen=True, slots=True)
class AgentSchedule:
    entries: tuple[ScheduleEntry, ...]
    overrides: dict[str, tuple[ScheduleEntry, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.entries:
            raise ValueError("schedule requires entries")
        if tuple(sorted(self.entries, key=lambda entry: entry.minute)) != self.entries:
            raise ValueError("schedule entries must be sorted")

    def activity_at(self, minute: int, *, contexts: Iterable[str] = ()) -> ScheduleEntry:
        minute %= 24 * 60
        candidates = list(self.entries)
        for context in contexts:
            candidates.extend(self.overrides.get(context, ()))
        candidates.sort(key=lambda entry: entry.minute)
        chosen = candidates[-1]
        for entry in candidates:
            if entry.minute <= minute:
                chosen = entry
            else:
                break
        return chosen


@dataclass(slots=True)
class WorldAgent:
    id: str
    node_id: str
    schedule: AgentSchedule
    path: tuple[str, ...] = ()
    path_index: int = 0

    def plan_to(self, graph: NavigationGraph, destination: str) -> tuple[str, ...]:
        self.path = graph.shortest_path(self.node_id, destination)
        self.path_index = 0
        return self.path

    def advance(self) -> str:
        if not self.path:
            return self.node_id
        if self.path_index < len(self.path) - 1:
            self.path_index += 1
            self.node_id = self.path[self.path_index]
        return self.node_id

    def sync_schedule(
        self,
        graph: NavigationGraph,
        minute: int,
        *,
        contexts: Iterable[str] = (),
    ) -> ScheduleEntry:
        activity = self.schedule.activity_at(minute, contexts=contexts)
        if activity.location != self.node_id:
            self.plan_to(graph, activity.location)
        return activity
