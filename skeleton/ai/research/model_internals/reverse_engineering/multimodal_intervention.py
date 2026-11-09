"""Cross-modal intervention consistency for authorized paired experiments."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class MultimodalInterventionObservation:
    observation_id: str
    semantic_digest: str
    modality: str
    intervention_kind: str
    baseline_metric: float
    intervened_metric: float

    def __post_init__(self) -> None:
        if not self.observation_id or not self.modality or not self.intervention_kind:
            raise ReverseEngineeringError("multimodal intervention identity is required")
        if not is_sha256_digest(self.semantic_digest):
            raise ReverseEngineeringError("semantic_digest must be sha256 hex")
        if not isfinite(self.baseline_metric) or not isfinite(self.intervened_metric):
            raise ReverseEngineeringError("multimodal intervention metrics must be finite")

    @property
    def effect(self) -> float:
        return self.intervened_metric - self.baseline_metric


@dataclass(frozen=True)
class MultimodalInterventionReport:
    intervention_kind: str
    modality_count: int
    semantic_pair_count: int
    mean_effect_by_modality: tuple[tuple[str, float], ...]
    sign_agreement_ratio: float
    mean_effect_range: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "intervention_kind": self.intervention_kind,
            "modality_count": self.modality_count,
            "semantic_pair_count": self.semantic_pair_count,
            "mean_effect_by_modality": [list(item) for item in self.mean_effect_by_modality],
            "sign_agreement_ratio": self.sign_agreement_ratio,
            "mean_effect_range": self.mean_effect_range,
            "digest": self.digest,
        }


def analyze_multimodal_intervention_consistency(
    observations: Sequence[MultimodalInterventionObservation],
) -> tuple[MultimodalInterventionReport, ...]:
    if not observations:
        raise ReverseEngineeringError("multimodal intervention analysis requires observations")
    by_kind: dict[str, list[MultimodalInterventionObservation]] = {}
    for item in observations:
        by_kind.setdefault(item.intervention_kind, []).append(item)

    reports: list[MultimodalInterventionReport] = []
    for kind, items in sorted(by_kind.items()):
        by_modality: dict[str, list[float]] = {}
        by_semantic: dict[str, list[MultimodalInterventionObservation]] = {}
        for item in items:
            by_modality.setdefault(item.modality, []).append(item.effect)
            by_semantic.setdefault(item.semantic_digest, []).append(item)

        means = tuple(
            sorted(
                (modality, sum(values) / len(values))
                for modality, values in by_modality.items()
            )
        )
        agreements = 0
        comparable = 0
        for semantic_items in by_semantic.values():
            effects = [item.effect for item in semantic_items]
            signs = {0 if value == 0 else (1 if value > 0 else -1) for value in effects}
            if len(effects) >= 2:
                comparable += 1
                if len(signs) == 1:
                    agreements += 1
        mean_values = [value for _, value in means]
        payload = {
            "intervention_kind": kind,
            "observations": [
                {
                    "observation_id": item.observation_id,
                    "semantic_digest": item.semantic_digest,
                    "modality": item.modality,
                    "baseline_metric": item.baseline_metric,
                    "intervened_metric": item.intervened_metric,
                }
                for item in sorted(items, key=lambda value: value.observation_id)
            ],
        }
        reports.append(
            MultimodalInterventionReport(
                intervention_kind=kind,
                modality_count=len(by_modality),
                semantic_pair_count=comparable,
                mean_effect_by_modality=means,
                sign_agreement_ratio=(agreements / comparable if comparable else 0.0),
                mean_effect_range=(max(mean_values) - min(mean_values) if mean_values else 0.0),
                digest=stable_digest(payload),
            )
        )
    return tuple(reports)
