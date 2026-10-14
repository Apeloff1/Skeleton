"""Conservative confidence aggregation across independent quality dimensions."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class ConfidenceComponent:
    name: str
    value: float
    weight: float = 1.0
    mandatory: bool = True

    def __post_init__(self) -> None:
        if not self.name:
            raise ReverseEngineeringError("confidence component requires name")
        if not isfinite(self.value) or not 0.0 <= self.value <= 1.0:
            raise ReverseEngineeringError("confidence component value must be within [0, 1]")
        if not isfinite(self.weight) or self.weight <= 0.0:
            raise ReverseEngineeringError("confidence component weight must be positive")


@dataclass(frozen=True)
class EvidenceConfidenceReport:
    component_count: int
    mandatory_floor: float
    weighted_mean: float
    conservative_score: float
    weakest_component: str
    weakest_value: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "component_count": self.component_count,
            "mandatory_floor": self.mandatory_floor,
            "weighted_mean": self.weighted_mean,
            "conservative_score": self.conservative_score,
            "weakest_component": self.weakest_component,
            "weakest_value": self.weakest_value,
            "digest": self.digest,
        }


def aggregate_evidence_confidence(
    components: Mapping[str, ConfidenceComponent] | tuple[ConfidenceComponent, ...],
) -> EvidenceConfidenceReport:
    if isinstance(components, Mapping):
        items = tuple(components.values())
    else:
        items = tuple(components)
    if not items:
        raise ReverseEngineeringError("confidence aggregation requires components")
    names = [item.name for item in items]
    if len(names) != len(set(names)):
        raise ReverseEngineeringError("confidence component names must be unique")

    mandatory = [item.value for item in items if item.mandatory]
    floor = min(mandatory) if mandatory else 1.0
    total_weight = sum(item.weight for item in items)
    weighted = sum(item.value * item.weight for item in items) / total_weight
    conservative = min(floor, weighted)
    weakest = min(items, key=lambda item: (item.value, item.name))
    payload = {
        "components": [
            {
                "name": item.name,
                "value": item.value,
                "weight": item.weight,
                "mandatory": item.mandatory,
            }
            for item in sorted(items, key=lambda value: value.name)
        ]
    }
    return EvidenceConfidenceReport(
        component_count=len(items),
        mandatory_floor=floor,
        weighted_mean=weighted,
        conservative_score=conservative,
        weakest_component=weakest.name,
        weakest_value=weakest.value,
        digest=stable_digest(payload),
    )
