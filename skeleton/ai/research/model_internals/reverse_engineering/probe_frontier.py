"""Pareto frontier for probe cost, information value, and risk."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class FrontierProbe:
    probe_id: str
    cost: float
    information_value: float
    risk: float

    def __post_init__(self) -> None:
        if not self.probe_id:
            raise ReverseEngineeringError("frontier probe requires identity")
        for value, name in (
            (self.cost, "cost"),
            (self.information_value, "information_value"),
            (self.risk, "risk"),
        ):
            if not isfinite(value) or value < 0.0:
                raise ReverseEngineeringError(f"{name} must be finite and non-negative")


@dataclass(frozen=True)
class ProbeFrontierReport:
    probe_count: int
    frontier_ids: tuple[str, ...]
    dominated_ids: tuple[str, ...]
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "probe_count": self.probe_count,
            "frontier_ids": list(self.frontier_ids),
            "dominated_ids": list(self.dominated_ids),
            "digest": self.digest,
        }


def _dominates(left: FrontierProbe, right: FrontierProbe) -> bool:
    no_worse = (
        left.cost <= right.cost
        and left.risk <= right.risk
        and left.information_value >= right.information_value
    )
    strictly_better = (
        left.cost < right.cost
        or left.risk < right.risk
        or left.information_value > right.information_value
    )
    return no_worse and strictly_better


def analyze_probe_frontier(
    probes: Sequence[FrontierProbe],
) -> ProbeFrontierReport:
    if not probes:
        raise ReverseEngineeringError("probe frontier requires probes")
    ids = [probe.probe_id for probe in probes]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("frontier probe ids must be unique")
    frontier = []
    dominated = []
    for probe in probes:
        if any(
            other.probe_id != probe.probe_id and _dominates(other, probe)
            for other in probes
        ):
            dominated.append(probe.probe_id)
        else:
            frontier.append(probe.probe_id)
    payload = {
        "probes": [
            {
                "probe_id": probe.probe_id,
                "cost": probe.cost,
                "information_value": probe.information_value,
                "risk": probe.risk,
            }
            for probe in sorted(probes, key=lambda value: value.probe_id)
        ]
    }
    return ProbeFrontierReport(
        probe_count=len(probes),
        frontier_ids=tuple(sorted(frontier)),
        dominated_ids=tuple(sorted(dominated)),
        digest=stable_digest(payload),
    )
