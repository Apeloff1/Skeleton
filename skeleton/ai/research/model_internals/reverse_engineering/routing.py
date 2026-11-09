"""Observable routing fingerprint analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class RoutingObservation:
    observation_id: str
    input_class: str
    route_label: str
    response_digest: str
    latency_bucket: str = "unknown"
    feature_flags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.observation_id or not self.input_class or not self.route_label:
            raise ReverseEngineeringError("routing observation identity fields are required")
        if len(self.response_digest) != 64:
            raise ReverseEngineeringError("response_digest must be sha256 length")
        object.__setattr__(self, "feature_flags", tuple(sorted(set(self.feature_flags))))


@dataclass(frozen=True)
class RoutingFingerprint:
    observation_count: int
    route_counts: tuple[tuple[str, int], ...]
    class_routes: tuple[tuple[str, tuple[str, ...]], ...]
    route_entropy_proxy: float
    deterministic_class_ratio: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "observation_count": self.observation_count,
            "route_counts": [list(item) for item in self.route_counts],
            "class_routes": [[key, list(routes)] for key, routes in self.class_routes],
            "route_entropy_proxy": self.route_entropy_proxy,
            "deterministic_class_ratio": self.deterministic_class_ratio,
            "digest": self.digest,
        }


def routing_fingerprint(observations: Sequence[RoutingObservation]) -> RoutingFingerprint:
    if not observations:
        raise ReverseEngineeringError("routing fingerprint requires observations")
    route_counts: dict[str, int] = {}
    class_routes: dict[str, set[str]] = {}
    for item in observations:
        route_counts[item.route_label] = route_counts.get(item.route_label, 0) + 1
        class_routes.setdefault(item.input_class, set()).add(item.route_label)

    total = len(observations)
    concentration = sum((count / total) ** 2 for count in route_counts.values())
    entropy_proxy = 1.0 - concentration
    deterministic = sum(1 for routes in class_routes.values() if len(routes) == 1)
    deterministic_ratio = deterministic / len(class_routes)
    class_routes_tuple = tuple(
        (name, tuple(sorted(routes))) for name, routes in sorted(class_routes.items())
    )
    payload = {
        "observations": [
            {
                "id": item.observation_id,
                "class": item.input_class,
                "route": item.route_label,
                "response": item.response_digest,
                "latency": item.latency_bucket,
                "flags": list(item.feature_flags),
            }
            for item in sorted(observations, key=lambda value: value.observation_id)
        ]
    }
    return RoutingFingerprint(
        observation_count=total,
        route_counts=tuple(sorted(route_counts.items())),
        class_routes=class_routes_tuple,
        route_entropy_proxy=entropy_proxy,
        deterministic_class_ratio=deterministic_ratio,
        digest=stable_digest(payload),
    )
