"""Layer-localization summaries for causal intervention effects."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class LayerInterventionEffect:
    observation_id: str
    probe_digest: str
    layer_index: int
    effect: float

    def __post_init__(self) -> None:
        if not self.observation_id:
            raise ReverseEngineeringError("layer intervention effect requires identity")
        if not is_sha256_digest(self.probe_digest):
            raise ReverseEngineeringError("probe_digest must be a sha256 hex digest")
        if self.layer_index < 0:
            raise ReverseEngineeringError("layer_index must be non-negative")
        if not isfinite(self.effect):
            raise ReverseEngineeringError("effect must be finite")


@dataclass(frozen=True)
class InterventionLocalizationReport:
    layer_count: int
    observation_count: int
    peak_layer: int
    peak_mean_effect: float
    absolute_effect_concentration: float
    effect_weighted_layer_centroid: float | None
    sign_consistency_at_peak: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "layer_count": self.layer_count,
            "observation_count": self.observation_count,
            "peak_layer": self.peak_layer,
            "peak_mean_effect": self.peak_mean_effect,
            "absolute_effect_concentration": self.absolute_effect_concentration,
            "effect_weighted_layer_centroid": self.effect_weighted_layer_centroid,
            "sign_consistency_at_peak": self.sign_consistency_at_peak,
            "digest": self.digest,
        }


def analyze_intervention_localization(
    effects: Sequence[LayerInterventionEffect],
) -> InterventionLocalizationReport:
    if not effects:
        raise ReverseEngineeringError("intervention localization requires effects")
    probe_digests = {item.probe_digest for item in effects}
    if len(probe_digests) != 1:
        raise ReverseEngineeringError("intervention effects must share probe_digest")
    grouped: dict[int, list[float]] = {}
    for item in effects:
        grouped.setdefault(item.layer_index, []).append(item.effect)
    means = {layer: sum(values) / len(values) for layer, values in grouped.items()}
    peak_layer = max(means, key=lambda layer: (abs(means[layer]), -layer))
    peak_mean = means[peak_layer]
    absolute = {layer: abs(value) for layer, value in means.items()}
    total_abs = sum(absolute.values())
    concentration = absolute[peak_layer] / total_abs if total_abs else 0.0
    centroid = (
        sum(layer * weight for layer, weight in absolute.items()) / total_abs
        if total_abs
        else None
    )
    peak_values = grouped[peak_layer]
    if peak_mean > 0:
        consistent = sum(value > 0 for value in peak_values) / len(peak_values)
    elif peak_mean < 0:
        consistent = sum(value < 0 for value in peak_values) / len(peak_values)
    else:
        consistent = sum(value == 0 for value in peak_values) / len(peak_values)
    payload = {
        "probe_digest": next(iter(probe_digests)),
        "effects": [
            {
                "observation_id": item.observation_id,
                "layer_index": item.layer_index,
                "effect": item.effect,
            }
            for item in sorted(effects, key=lambda value: value.observation_id)
        ],
    }
    return InterventionLocalizationReport(
        layer_count=len(grouped),
        observation_count=len(effects),
        peak_layer=peak_layer,
        peak_mean_effect=peak_mean,
        absolute_effect_concentration=concentration,
        effect_weighted_layer_centroid=centroid,
        sign_consistency_at_peak=consistent,
        digest=stable_digest(payload),
    )
