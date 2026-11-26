"""Deterministic route synthesis across a world-family graph.

The route is the admitted transition sequence found by breadth-first search.
Outgoing worlds are expanded in sorted identifier order, so the same graph and
the same traveler state always produce the same hops. Search does not use
randomness or a clock.

An impossible route is a :class:`RouteRefusal` naming the first broken
constraint on the shortest structural path. It is not an empty route.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from skeleton.frontier_worldgraph.graph import (
    AdmittedTransition,
    Constraint,
    TransitionRefusal,
    Traveler,
    WorldFamilyGraph,
    WorldGraphError,
    WorldNode,
    climate_overlaps,
)


@dataclass(frozen=True, slots=True)
class Route:
    """A sequence of admitted transitions from ``origin_id`` to ``goal_id``."""

    origin_id: str
    goal_id: str
    transitions: tuple[AdmittedTransition, ...]
    traveler: Traveler

    def __post_init__(self) -> None:
        if not isinstance(self.traveler, Traveler):
            raise WorldGraphError("route traveler is missing")
        if not isinstance(self.transitions, tuple) or any(
            not isinstance(hop, AdmittedTransition) for hop in self.transitions
        ):
            raise WorldGraphError("route transitions must be admitted hops")
        cursor = self.origin_id
        for hop in self.transitions:
            if hop.source_id != cursor:
                raise WorldGraphError("route hops do not connect")
            cursor = hop.destination_id
        if cursor != self.goal_id or self.traveler.world_id != self.goal_id:
            raise WorldGraphError("route does not arrive at the goal")
        if self.transitions:
            if self.traveler != self.transitions[-1].traveler:
                raise WorldGraphError("route traveler does not match the last hop")
        elif self.origin_id != self.goal_id:
            raise WorldGraphError("an empty route is not a successful traversal")

    @property
    def addresses(self) -> tuple[str, ...]:
        return tuple(hop.address for hop in self.transitions)

    @property
    def world_ids(self) -> tuple[str, ...]:
        ids = [self.origin_id]
        for hop in self.transitions:
            ids.append(hop.destination_id)
        return tuple(ids)

    @property
    def hop_count(self) -> int:
        """Operator cost of the route: one unit per admitted transition."""

        return len(self.transitions)


@dataclass(frozen=True, slots=True)
class RouteRefusal:
    """Impossible route. The traveler is still in the origin world."""

    constraint: Constraint
    origin_id: str
    goal_id: str
    broken_source_id: str
    broken_destination_id: str | None
    traveler: Traveler
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.constraint, Constraint):
            raise WorldGraphError("route refusal constraint is not typed")
        if not isinstance(self.traveler, Traveler):
            raise WorldGraphError("route refusal must carry the traveler")
        if self.traveler.world_id != self.origin_id:
            raise WorldGraphError("a refused route moved the traveler")
        if self.broken_source_id != self.origin_id and self.constraint is Constraint.DISCONNECTED:
            raise WorldGraphError("disconnected refusal left the origin")
        if self.constraint is Constraint.DISCONNECTED:
            if self.broken_destination_id is not None:
                raise WorldGraphError("a disconnected route names a destination")
        elif not isinstance(self.broken_destination_id, str) or self.broken_destination_id == "":
            raise WorldGraphError("refusal is missing the broken destination")
        if not isinstance(self.detail, str) or self.detail == "":
            raise WorldGraphError("refusal detail must be text")


def synthesize_route(
    graph: WorldFamilyGraph, traveler: Traveler, goal_id: str
) -> Route | RouteRefusal:
    """Return the admitted route, or a typed refusal for the first broken constraint."""

    if not isinstance(graph, WorldFamilyGraph):
        raise WorldGraphError("route synthesis requires a world-family graph")
    if not isinstance(traveler, Traveler):
        raise WorldGraphError("traveler must be a Traveler")
    goal = graph.world(goal_id)
    origin = graph.world(traveler.world_id)
    if origin.world_id == goal.world_id:
        return _remain(traveler, origin)
    previous: dict[str, AdmittedTransition] = {}
    seen = {origin.world_id}
    queue: deque[Traveler] = deque([traveler])
    while queue:
        current = queue.popleft()
        for destination_id in graph.destinations(current.world_id):
            if destination_id in seen:
                continue
            outcome = graph.cross(current, destination_id)
            if not isinstance(outcome, AdmittedTransition):
                continue
            seen.add(destination_id)
            previous[destination_id] = outcome
            if destination_id == goal.world_id:
                return _assemble(origin.world_id, goal.world_id, previous, outcome.traveler)
            queue.append(outcome.traveler)
    return _first_structural_refusal(graph, traveler, origin.world_id, goal.world_id)


def follow(
    graph: WorldFamilyGraph, traveler: Traveler, route: Route
) -> Traveler | RouteRefusal:
    """Re-admit every hop. A broken hop leaves the original traveler in place."""

    if not isinstance(route, Route):
        raise WorldGraphError("follow requires an admitted route")
    if not isinstance(traveler, Traveler):
        raise WorldGraphError("traveler must be a Traveler")
    if traveler.world_id != route.origin_id:
        raise WorldGraphError("route does not start at the traveler")
    current = traveler
    for hop in route.transitions:
        outcome = graph.cross(current, hop.destination_id)
        if isinstance(outcome, TransitionRefusal):
            return RouteRefusal(
                constraint=outcome.constraint,
                origin_id=traveler.world_id,
                goal_id=route.goal_id,
                broken_source_id=outcome.source_id,
                broken_destination_id=outcome.destination_id,
                traveler=traveler,
                detail=outcome.detail,
            )
        if outcome.address != hop.address:
            raise WorldGraphError("route edge content address drifted")
        current = outcome.traveler
    if current.world_id != route.goal_id:
        raise WorldGraphError("route did not arrive at the goal")
    return current


def _remain(traveler: Traveler, world: WorldNode) -> Route | RouteRefusal:
    constraint = _occupancy(traveler, world)
    if constraint is None:
        return Route(
            origin_id=world.world_id,
            goal_id=world.world_id,
            transitions=(),
            traveler=traveler,
        )
    return RouteRefusal(
        constraint=constraint,
        origin_id=world.world_id,
        goal_id=world.world_id,
        broken_source_id=world.world_id,
        broken_destination_id=world.world_id,
        traveler=traveler,
        detail=_OCCUPANCY_DETAIL[constraint],
    )


def _occupancy(traveler: Traveler, world: WorldNode) -> Constraint | None:
    if traveler.identity != world.identity:
        return Constraint.IDENTITY
    if traveler.canon_digest != world.canon_digest:
        return Constraint.CANON
    if not climate_overlaps(world.climate, traveler.envelope):
        return Constraint.CLIMATE
    if traveler.rule_ids != world.rule_ids:
        return Constraint.PHYSICS
    if traveler.position.layer is not world.position.layer:
        raise WorldGraphError("traveler layer does not match the occupied world")
    return None


def _assemble(
    origin_id: str,
    goal_id: str,
    previous: dict[str, AdmittedTransition],
    traveler: Traveler,
) -> Route:
    hops: list[AdmittedTransition] = []
    cursor = goal_id
    guard = 0
    while cursor != origin_id:
        hop = previous[cursor]
        hops.append(hop)
        cursor = hop.source_id
        guard += 1
        if guard > len(previous):
            raise WorldGraphError("route reconstruction failed to reach the origin")
    hops.reverse()
    return Route(origin_id, goal_id, tuple(hops), traveler)


def _first_structural_refusal(
    graph: WorldFamilyGraph,
    traveler: Traveler,
    origin_id: str,
    goal_id: str,
) -> RouteRefusal:
    came: dict[str, str] = {}
    seen = {origin_id}
    queue: deque[str] = deque([origin_id])
    while queue:
        current = queue.popleft()
        if current == goal_id:
            break
        for destination_id in graph.destinations(current):
            if destination_id in seen:
                continue
            seen.add(destination_id)
            came[destination_id] = current
            queue.append(destination_id)
    if goal_id not in came:
        return RouteRefusal(
            constraint=Constraint.DISCONNECTED,
            origin_id=origin_id,
            goal_id=goal_id,
            broken_source_id=origin_id,
            broken_destination_id=None,
            traveler=traveler,
            detail="no declared transition reaches the destination",
        )
    path = [goal_id]
    while path[-1] != origin_id:
        path.append(came[path[-1]])
        if len(path) > len(came) + 1:
            raise WorldGraphError("structural path reconstruction failed")
    path.reverse()
    current = traveler
    for destination_id in path[1:]:
        outcome = graph.cross(current, destination_id)
        if isinstance(outcome, TransitionRefusal):
            return RouteRefusal(
                constraint=outcome.constraint,
                origin_id=origin_id,
                goal_id=goal_id,
                broken_source_id=outcome.source_id,
                broken_destination_id=outcome.destination_id,
                traveler=traveler,
                detail=outcome.detail,
            )
        current = outcome.traveler
    raise WorldGraphError("admitted search missed a fully admitted structural route")


_OCCUPANCY_DETAIL = {
    Constraint.IDENTITY: "identity is not preserved",
    Constraint.CANON: "canon digest does not match the occupied world",
    Constraint.CLIMATE: "climate bounds do not overlap the carried envelope",
    Constraint.PHYSICS: "physical-rule set is not the occupied world's rules",
}
