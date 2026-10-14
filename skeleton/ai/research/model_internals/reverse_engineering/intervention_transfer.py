"""Transfer consistency for matched interventions across authorized models."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class TransferObservation:
    observation_id: str
    intervention_digest: str
    model_id: str
    semantic_digest: str
    effect: float

    def __post_init__(self) -> None:
        if not self.observation_id or not self.model_id:
            raise ReverseEngineeringError("transfer observation identity is required")
        if not is_sha256_digest(self.intervention_digest) or not is_sha256_digest(self.semantic_digest):
            raise ReverseEngineeringError("transfer digests must be sha256 hex")
        if not isfinite(self.effect):
            raise ReverseEngineeringError("transfer effect must be finite")


@dataclass(frozen=True)
class InterventionTransferReport:
    model_count: int
    semantic_case_count: int
    mean_effect_by_model: tuple[tuple[str, float], ...]
    sign_agreement_ratio: float
    effect_range: float
    transferable: bool
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_count": self.model_count,
            "semantic_case_count": self.semantic_case_count,
            "mean_effect_by_model": [list(item) for item in self.mean_effect_by_model],
            "sign_agreement_ratio": self.sign_agreement_ratio,
            "effect_range": self.effect_range,
            "transferable": self.transferable,
            "digest": self.digest,
        }


def analyze_intervention_transfer(
    observations: Sequence[TransferObservation],
    *,
    minimum_sign_agreement_ratio: float = 0.8,
) -> InterventionTransferReport:
    if not observations:
        raise ReverseEngineeringError("intervention transfer requires observations")
    if not 0.0 <= minimum_sign_agreement_ratio <= 1.0:
        raise ReverseEngineeringError("minimum_sign_agreement_ratio must be within [0, 1]")
    interventions = {item.intervention_digest for item in observations}
    if len(interventions) != 1:
        raise ReverseEngineeringError("transfer observations must share intervention_digest")

    by_model: dict[str, list[float]] = {}
    by_semantic: dict[str, list[TransferObservation]] = {}
    for item in observations:
        by_model.setdefault(item.model_id, []).append(item.effect)
        by_semantic.setdefault(item.semantic_digest, []).append(item)
    model_means = tuple(sorted((model, sum(values) / len(values)) for model, values in by_model.items()))
    comparable = 0
    agreeing = 0
    for items in by_semantic.values():
        if len(items) < 2:
            continue
        comparable += 1
        signs = {0 if item.effect == 0.0 else (1 if item.effect > 0.0 else -1) for item in items}
        if len(signs) == 1:
            agreeing += 1
    agreement = agreeing / comparable if comparable else 0.0
    values = [value for _, value in model_means]
    payload = {
        "intervention_digest": next(iter(interventions)),
        "minimum_sign_agreement_ratio": minimum_sign_agreement_ratio,
        "observations": [
            {
                "observation_id": item.observation_id,
                "model_id": item.model_id,
                "semantic_digest": item.semantic_digest,
                "effect": item.effect,
            }
            for item in sorted(observations, key=lambda value: value.observation_id)
        ],
    }
    return InterventionTransferReport(
        model_count=len(by_model),
        semantic_case_count=comparable,
        mean_effect_by_model=model_means,
        sign_agreement_ratio=agreement,
        effect_range=(max(values) - min(values) if values else 0.0),
        transferable=agreement >= minimum_sign_agreement_ratio,
        digest=stable_digest(payload),
    )
