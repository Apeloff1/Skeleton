"""Directional asymmetry summaries for paired causal interventions."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class DirectionalEffect:
    observation_id: str
    probe_digest: str
    source: str
    target: str
    effect: float

    def __post_init__(self) -> None:
        if not self.observation_id or not self.source or not self.target:
            raise ReverseEngineeringError("directional effect identity is required")
        if self.source == self.target:
            raise ReverseEngineeringError("directional effect requires distinct nodes")
        if not is_sha256_digest(self.probe_digest):
            raise ReverseEngineeringError("probe_digest must be sha256 hex")
        if not isfinite(self.effect):
            raise ReverseEngineeringError("directional effect must be finite")


@dataclass(frozen=True)
class DirectionalityReport:
    node_a: str
    node_b: str
    a_to_b_count: int
    b_to_a_count: int
    mean_a_to_b: float | None
    mean_b_to_a: float | None
    asymmetry: float | None
    dominant_direction: str | None
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "node_a": self.node_a,
            "node_b": self.node_b,
            "a_to_b_count": self.a_to_b_count,
            "b_to_a_count": self.b_to_a_count,
            "mean_a_to_b": self.mean_a_to_b,
            "mean_b_to_a": self.mean_b_to_a,
            "asymmetry": self.asymmetry,
            "dominant_direction": self.dominant_direction,
            "digest": self.digest,
        }


def analyze_causal_directionality(
    effects: Sequence[DirectionalEffect],
) -> tuple[DirectionalityReport, ...]:
    if not effects:
        raise ReverseEngineeringError("causal directionality requires effects")
    grouped: dict[tuple[str, str], list[DirectionalEffect]] = {}
    for effect in effects:
        key = tuple(sorted((effect.source, effect.target)))
        grouped.setdefault(key, []).append(effect)

    reports: list[DirectionalityReport] = []
    for (a, b), items in sorted(grouped.items()):
        probe_digests = {item.probe_digest for item in items}
        if len(probe_digests) != 1:
            raise ReverseEngineeringError("directionality pair must share probe_digest")
        ab = [item.effect for item in items if item.source == a and item.target == b]
        ba = [item.effect for item in items if item.source == b and item.target == a]
        mean_ab = sum(ab) / len(ab) if ab else None
        mean_ba = sum(ba) / len(ba) if ba else None
        asymmetry = None
        dominant = None
        if mean_ab is not None and mean_ba is not None:
            asymmetry = abs(mean_ab) - abs(mean_ba)
            if asymmetry > 0:
                dominant = f"{a}->{b}"
            elif asymmetry < 0:
                dominant = f"{b}->{a}"
            else:
                dominant = "symmetric"
        payload = {
            "node_a": a,
            "node_b": b,
            "probe_digest": next(iter(probe_digests)),
            "effects": [
                {
                    "observation_id": item.observation_id,
                    "source": item.source,
                    "target": item.target,
                    "effect": item.effect,
                }
                for item in sorted(items, key=lambda value: value.observation_id)
            ],
        }
        reports.append(
            DirectionalityReport(
                node_a=a,
                node_b=b,
                a_to_b_count=len(ab),
                b_to_a_count=len(ba),
                mean_a_to_b=mean_ab,
                mean_b_to_a=mean_ba,
                asymmetry=asymmetry,
                dominant_direction=dominant,
                digest=stable_digest(payload),
            )
        )
    return tuple(reports)
