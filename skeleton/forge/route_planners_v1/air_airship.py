"""airship deterministic graph routing profile.

Graph search preserves stable ordering and refuses unknown nodes, invalid
budgets, non-positive edge costs and stale route publication. This is a
game-world planner rather than physical vehicle navigation.
"""
from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush
from typing import Any

SCHEMA = "skeleton.route_planner.v1"
ROUTE_ID = "air_airship"
DOMAIN = "air"
MODE = "ride"
NODES = ("start", "crossroads", "safehouse", "lookout", "goal")
EDGES = (
    ("start", "crossroads", 7, 1, 9),
    ("crossroads", "goal", 9, 2, 10),
    ("start", "safehouse", 9, 0, 11),
    ("safehouse", "goal", 10, 0, 9),
    ("crossroads", "lookout", 6, 4, 10),
    ("lookout", "goal", 7, 4, 9),
    ("safehouse", "crossroads", 7, 1, 9),
    ("start", "goal", 17, 7, 13),
)
MAX_BUDGET = 100000
MAX_HOPS = 16


@dataclass(frozen=True, slots=True)
class Route:
    nodes: tuple[str, ...]
    distance: int
    danger: int
    energy: int
    cost: int
    weights: tuple[int, int, int] = (1, 2, 1)

    def __post_init__(self) -> None:
        if type(self.nodes) is not tuple or not self.nodes:
            raise ValueError("invalid-route-nodes")
        if any(type(n) is not str or n not in NODES for n in self.nodes):
            raise ValueError("invalid-route-node")
        if any(type(x) is not int or x < 0 for x in (
            self.distance, self.danger, self.energy, self.cost
        )):
            raise ValueError("invalid-route-metric")
        if (type(self.weights) is not tuple or len(self.weights) != 3
                or any(type(w) is not int or not 0 <= w <= MAX_BUDGET for w in self.weights)
                or not any(self.weights)):
            raise ValueError("invalid-route-weights")


def _budget(value: int, label: str) -> int:
    if type(value) is not int or not 0 <= value <= MAX_BUDGET:
        raise ValueError("invalid-" + label)
    return value


def plan(
    origin: str = "start",
    destination: str = "goal",
    danger_budget: int = 100,
    energy_budget: int = 100,
    distance_weight: int = 1,
    danger_weight: int = 2,
    energy_weight: int = 1,
    blocked: tuple[str, ...] = (),
) -> Route | None:
    """Find minimum weighted route under three independent resource budgets.

    Candidate costs are strictly positive for inter-node links. Heap ordering
    includes complete path tuple for deterministic tie breaking.
    """
    if type(origin) is not str or origin not in NODES:
        raise ValueError("invalid-origin")
    if type(destination) is not str or destination not in NODES:
        raise ValueError("invalid-destination")
    for name, value in (
        ("danger-budget", danger_budget),
        ("energy-budget", energy_budget),
        ("distance-weight", distance_weight),
        ("danger-weight", danger_weight),
        ("energy-weight", energy_weight),
    ):
        _budget(value, name)
    if not any((distance_weight, danger_weight, energy_weight)):
        raise ValueError("zero-objective")
    if type(blocked) is not tuple or any(
        type(n) is not str or n not in NODES for n in blocked
    ) or len(set(blocked)) != len(blocked):
        raise ValueError("invalid-blocked-set")
    if origin in blocked or destination in blocked:
        return None
    if origin == destination:
        return Route((origin,), 0, 0, 0, 0, (distance_weight, danger_weight, energy_weight))

    adjacency: dict[str, list[tuple[str, int, int, int]]] = {
        node: [] for node in NODES
    }
    for left, right, distance, danger, energy in EDGES:
        adjacency[left].append((right, distance, danger, energy))
    for node in adjacency:
        adjacency[node].sort()

    # Do not deduplicate by node alone: resource-constrained paths with
    # different energy/danger consumption are not interchangeable.
    queue: list[tuple[int, tuple[str, ...], int, int, int]] = [
        (0, (origin,), 0, 0, 0)
    ]
    while queue:
        cost, path, distance, danger, energy = heappop(queue)
        node = path[-1]
        if node == destination:
            return Route(path, distance, danger, energy, cost, (distance_weight, danger_weight, energy_weight))
        if len(path) >= MAX_HOPS:
            continue
        for next_node, delta_distance, delta_danger, delta_energy in adjacency[node]:
            if next_node in blocked or next_node in path:
                continue
            next_danger = danger + delta_danger
            next_energy = energy + delta_energy
            if next_danger > danger_budget or next_energy > energy_budget:
                continue
            next_distance = distance + delta_distance
            next_cost = (
                distance_weight * next_distance
                + danger_weight * next_danger
                + energy_weight * next_energy
            )
            heappush(queue, (
                next_cost, path + (next_node,), next_distance,
                next_danger, next_energy,
            ))
    return None


def inspect() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "route_id": ROUTE_ID,
        "domain": DOMAIN,
        "mode": MODE,
        "nodes": list(NODES),
        "edge_count": len(EDGES),
        "directed": True,
        "budget_fields": ["danger", "energy"],
        "algorithm": "bounded-weighted-uniform-cost",
        "release_certified": False,
    }


def validate_route(route: Route, blocked: tuple[str, ...] = (), *,
                   expected_weights: tuple[int, int, int] | None = None) -> bool:
    """Verify returned edge sequence without trusting a client-supplied route."""
    if type(route) is not Route:
        return False
    if expected_weights is not None and route.weights != expected_weights:
        return False
    if type(blocked) is not tuple or any(
        type(n) is not str or n not in NODES for n in blocked
    ):
        return False
    if any(n in blocked for n in route.nodes):
        return False
    if len(route.nodes) > MAX_HOPS or len(set(route.nodes)) != len(route.nodes):
        return False
    distance = danger = energy = 0
    for left, right in zip(route.nodes, route.nodes[1:]):
        matching = [e for e in EDGES if e[0] == left and e[1] == right]
        if len(matching) != 1:
            return False
        edge = matching[0]
        distance += edge[2]
        danger += edge[3]
        energy += edge[4]
    return (
        distance == route.distance
        and danger == route.danger
        and energy == route.energy
        and route.cost == sum(metric * weight for metric, weight in zip(
            (distance, danger, energy), route.weights
        ))
    )
