"""Long-horizon routing stability from windowed route counts."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class RoutingWindow:
    window_id: str
    ordinal: int
    route_counts: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        if not self.window_id:
            raise ReverseEngineeringError("routing window requires window_id")
        if self.ordinal < 0:
            raise ReverseEngineeringError("routing window ordinal must be non-negative")
        if not self.route_counts:
            raise ReverseEngineeringError("routing window requires route counts")
        names = [name for name, _ in self.route_counts]
        if len(names) != len(set(names)):
            raise ReverseEngineeringError("route names must be unique within a window")
        if any(not name or count < 0 for name, count in self.route_counts):
            raise ReverseEngineeringError("route names must be non-empty and counts non-negative")
        if sum(count for _, count in self.route_counts) <= 0:
            raise ReverseEngineeringError("routing window must contain positive total count")


@dataclass(frozen=True)
class RoutingStabilityReport:
    window_count: int
    route_count: int
    mean_adjacent_total_variation: float
    max_adjacent_total_variation: float
    dominant_route_change_count: int
    stable_below_threshold_ratio: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "window_count": self.window_count,
            "route_count": self.route_count,
            "mean_adjacent_total_variation": self.mean_adjacent_total_variation,
            "max_adjacent_total_variation": self.max_adjacent_total_variation,
            "dominant_route_change_count": self.dominant_route_change_count,
            "stable_below_threshold_ratio": self.stable_below_threshold_ratio,
            "digest": self.digest,
        }


def _distribution(window: RoutingWindow, routes: Sequence[str]) -> dict[str, float]:
    counts = dict(window.route_counts)
    total = sum(counts.values())
    return {route: counts.get(route, 0) / total for route in routes}


def analyze_routing_stability(
    windows: Sequence[RoutingWindow],
    *,
    stable_threshold: float = 0.1,
) -> RoutingStabilityReport:
    if len(windows) < 2:
        raise ReverseEngineeringError("routing stability requires at least two windows")
    if not isfinite(stable_threshold) or not 0.0 <= stable_threshold <= 1.0:
        raise ReverseEngineeringError("stable_threshold must be finite and within [0, 1]")
    ordered = sorted(windows, key=lambda item: (item.ordinal, item.window_id))
    ordinals = [item.ordinal for item in ordered]
    if len(ordinals) != len(set(ordinals)):
        raise ReverseEngineeringError("routing window ordinals must be unique")
    routes = sorted({name for item in ordered for name, _ in item.route_counts})
    distributions = [_distribution(item, routes) for item in ordered]
    variations: list[float] = []
    dominant: list[str] = []
    for dist in distributions:
        dominant.append(max(routes, key=lambda route: (dist[route], route)))
    for left, right in zip(distributions, distributions[1:]):
        variations.append(0.5 * sum(abs(left[route] - right[route]) for route in routes))
    payload = {
        "stable_threshold": stable_threshold,
        "windows": [
            {"window_id": item.window_id, "ordinal": item.ordinal, "route_counts": list(item.route_counts)}
            for item in ordered
        ],
    }
    return RoutingStabilityReport(
        window_count=len(ordered),
        route_count=len(routes),
        mean_adjacent_total_variation=sum(variations) / len(variations),
        max_adjacent_total_variation=max(variations),
        dominant_route_change_count=sum(a != b for a, b in zip(dominant, dominant[1:])),
        stable_below_threshold_ratio=sum(value <= stable_threshold for value in variations) / len(variations),
        digest=stable_digest(payload),
    )
