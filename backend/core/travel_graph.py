"""World travel, discovery, and route planning primitives.

Mined from Newmove2's world-map system and redesigned as a deterministic graph
with discovery gates instead of route handlers and database coupling.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import heapq
from math import hypot
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class Region:
    id: str
    difficulty: int = 1
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Location:
    id: str
    region_id: str
    x: float
    y: float
    kind: str = "point"
    min_level: int = 1
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Route:
    a: str
    b: str
    distance: float
    danger: float = 0.0
    one_way: bool = False
    required_tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TravelPlan:
    locations: tuple[str, ...]
    distance: float
    danger: float
    cost: float


class TravelGraph:
    def __init__(self, regions: Iterable[Region], locations: Iterable[Location]) -> None:
        self.regions = {r.id: r for r in regions}
        self.locations = {p.id: p for p in locations}
        if not self.regions or not self.locations:
            raise ValueError("travel graph requires regions and locations")
        if any(not key.strip() for key in self.regions | self.locations):
            raise ValueError("blank travel id")
        if any(loc.region_id not in self.regions for loc in self.locations.values()):
            raise ValueError("location references unknown region")
        self._edges: dict[str, list[Route]] = {key: [] for key in self.locations}
        self.discovered: set[str] = set()

    def connect(
        self,
        a: str,
        b: str,
        *,
        distance: float | None = None,
        danger: float = 0.0,
        one_way: bool = False,
        required_tags: Iterable[str] = (),
    ) -> None:
        if a not in self.locations or b not in self.locations:
            raise KeyError("route endpoint is unknown")
        if a == b:
            raise ValueError("route endpoints must differ")
        resolved = float(distance) if distance is not None else hypot(
            self.locations[a].x - self.locations[b].x,
            self.locations[a].y - self.locations[b].y,
        )
        if resolved <= 0 or danger < 0:
            raise ValueError("invalid route distance or danger")
        tags = tuple(sorted(set(required_tags)))
        route = Route(a, b, resolved, float(danger), one_way, tags)
        self._edges[a].append(route)
        if not one_way:
            self._edges[b].append(Route(b, a, resolved, float(danger), one_way, tags))

    def discover(self, location_id: str) -> bool:
        if location_id not in self.locations:
            raise KeyError(location_id)
        before = len(self.discovered)
        self.discovered.add(location_id)
        return len(self.discovered) != before

    def available_locations(self, *, level: int, tags: Iterable[str] = ()) -> tuple[Location, ...]:
        owned = set(tags)
        return tuple(
            loc
            for loc in self.locations.values()
            if loc.min_level <= level and (not loc.tags or set(loc.tags).issubset(owned | set(loc.tags)))
        )

    def plan(
        self,
        start: str,
        end: str,
        *,
        level: int,
        tags: Iterable[str] = (),
        danger_weight: float = 1.0,
        discovered_only: bool = False,
    ) -> TravelPlan:
        if start not in self.locations or end not in self.locations:
            raise KeyError("unknown travel endpoint")
        if danger_weight < 0:
            raise ValueError("danger_weight cannot be negative")
        owned = set(tags)
        if self.locations[end].min_level > level:
            raise ValueError("destination level gate not met")
        if discovered_only and (start not in self.discovered or end not in self.discovered):
            raise ValueError("undiscovered endpoint")

        queue: list[tuple[float, str]] = [(0.0, start)]
        costs = {start: 0.0}
        distance_totals = {start: 0.0}
        danger_totals = {start: 0.0}
        previous: dict[str, str] = {}
        while queue:
            cost, node = heapq.heappop(queue)
            if cost != costs.get(node):
                continue
            if node == end:
                break
            for route in self._edges[node]:
                target = self.locations[route.b]
                if target.min_level > level:
                    continue
                if route.required_tags and not set(route.required_tags).issubset(owned):
                    continue
                if discovered_only and route.b not in self.discovered:
                    continue
                candidate = cost + route.distance + route.danger * danger_weight
                if candidate >= costs.get(route.b, float("inf")):
                    continue
                costs[route.b] = candidate
                distance_totals[route.b] = distance_totals[node] + route.distance
                danger_totals[route.b] = danger_totals[node] + route.danger
                previous[route.b] = node
                heapq.heappush(queue, (candidate, route.b))
        if end not in costs:
            raise ValueError("no reachable route")
        path = [end]
        while path[-1] != start:
            path.append(previous[path[-1]])
        path.reverse()
        return TravelPlan(
            tuple(path),
            distance_totals[end],
            danger_totals[end],
            costs[end],
        )

    def region_summary(self, region_id: str) -> dict[str, Any]:
        region = self.regions[region_id]
        locations = [loc for loc in self.locations.values() if loc.region_id == region_id]
        return {
            "id": region.id,
            "difficulty": region.difficulty,
            "tags": list(region.tags),
            "locations": len(locations),
            "discovered": sum(loc.id in self.discovered for loc in locations),
        }
