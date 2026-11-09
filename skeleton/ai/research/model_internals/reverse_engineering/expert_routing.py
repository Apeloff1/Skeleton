"""Mixture-of-experts routing characterization from observed expert selections."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class ExpertRoutingObservation:
    observation_id: str
    input_digest: str
    layer_index: int
    selected_experts: tuple[int, ...]
    routing_weights: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if not self.observation_id:
            raise ReverseEngineeringError("expert-routing observation requires identity")
        if not is_sha256_digest(self.input_digest):
            raise ReverseEngineeringError("input_digest must be a sha256 hex digest")
        if self.layer_index < 0:
            raise ReverseEngineeringError("layer_index must be non-negative")
        if not self.selected_experts:
            raise ReverseEngineeringError("selected_experts must be non-empty")
        if any(expert < 0 for expert in self.selected_experts):
            raise ReverseEngineeringError("expert ids must be non-negative")
        if len(set(self.selected_experts)) != len(self.selected_experts):
            raise ReverseEngineeringError("selected_experts must be unique")
        if self.routing_weights and len(self.routing_weights) != len(self.selected_experts):
            raise ReverseEngineeringError("routing_weights must align with selected_experts")
        if any(not isfinite(weight) or weight < 0.0 for weight in self.routing_weights):
            raise ReverseEngineeringError("routing weights must be finite and non-negative")


@dataclass(frozen=True)
class ExpertRoutingReport:
    layer_index: int
    observation_count: int
    experts_seen: tuple[int, ...]
    top_k_values: tuple[int, ...]
    selection_counts: tuple[tuple[int, int], ...]
    load_concentration: float
    mean_weight_sum: float | None
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "layer_index": self.layer_index,
            "observation_count": self.observation_count,
            "experts_seen": list(self.experts_seen),
            "top_k_values": list(self.top_k_values),
            "selection_counts": [list(item) for item in self.selection_counts],
            "load_concentration": self.load_concentration,
            "mean_weight_sum": self.mean_weight_sum,
            "digest": self.digest,
        }


def analyze_expert_routing(
    observations: Sequence[ExpertRoutingObservation],
) -> tuple[ExpertRoutingReport, ...]:
    if not observations:
        raise ReverseEngineeringError("expert-routing analysis requires observations")
    grouped: dict[int, list[ExpertRoutingObservation]] = {}
    for observation in observations:
        grouped.setdefault(observation.layer_index, []).append(observation)

    reports: list[ExpertRoutingReport] = []
    for layer_index, items in sorted(grouped.items()):
        ordered = sorted(items, key=lambda item: item.observation_id)
        counts: dict[int, int] = {}
        weighted_sums: list[float] = []
        total_selections = 0
        for item in ordered:
            for expert in item.selected_experts:
                counts[expert] = counts.get(expert, 0) + 1
                total_selections += 1
            if item.routing_weights:
                weighted_sums.append(sum(item.routing_weights))
        concentration = (
            sum((count / total_selections) ** 2 for count in counts.values())
            if total_selections
            else 0.0
        )
        payload = {
            "layer_index": layer_index,
            "observations": [
                {
                    "observation_id": item.observation_id,
                    "input_digest": item.input_digest,
                    "selected_experts": list(item.selected_experts),
                    "routing_weights": list(item.routing_weights),
                }
                for item in ordered
            ],
        }
        reports.append(
            ExpertRoutingReport(
                layer_index=layer_index,
                observation_count=len(ordered),
                experts_seen=tuple(sorted(counts)),
                top_k_values=tuple(sorted({len(item.selected_experts) for item in ordered})),
                selection_counts=tuple(sorted(counts.items())),
                load_concentration=concentration,
                mean_weight_sum=(
                    sum(weighted_sums) / len(weighted_sums) if weighted_sums else None
                ),
                digest=stable_digest(payload),
            )
        )
    return tuple(reports)
