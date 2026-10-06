"""Precision- and evidence-aware stopping rules for characterization campaigns."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class StoppingEvidence:
    sample_count: int
    confidence_interval_width: float | None
    effect_magnitude: float | None
    minimum_effect_of_interest: float
    replication_ratio: float | None
    contradiction_weight: float

    def __post_init__(self) -> None:
        if self.sample_count < 0:
            raise ReverseEngineeringError("sample_count must be non-negative")
        for value, name in (
            (self.confidence_interval_width, "confidence_interval_width"),
            (self.effect_magnitude, "effect_magnitude"),
            (self.replication_ratio, "replication_ratio"),
        ):
            if value is not None and (not isfinite(value) or value < 0.0):
                raise ReverseEngineeringError(f"{name} must be finite and non-negative")
        if not isfinite(self.minimum_effect_of_interest) or self.minimum_effect_of_interest < 0.0:
            raise ReverseEngineeringError("minimum_effect_of_interest must be finite and non-negative")
        if not isfinite(self.contradiction_weight) or not 0.0 <= self.contradiction_weight <= 1.0:
            raise ReverseEngineeringError("contradiction_weight must be within [0, 1]")


@dataclass(frozen=True)
class StoppingRule:
    minimum_samples: int = 20
    maximum_confidence_interval_width: float = 0.1
    minimum_replication_ratio: float = 0.8
    maximum_contradiction_weight: float = 0.2

    def __post_init__(self) -> None:
        if self.minimum_samples < 1:
            raise ReverseEngineeringError("minimum_samples must be positive")
        for value, name in (
            (self.maximum_confidence_interval_width, "maximum_confidence_interval_width"),
            (self.minimum_replication_ratio, "minimum_replication_ratio"),
            (self.maximum_contradiction_weight, "maximum_contradiction_weight"),
        ):
            if not isfinite(value) or value < 0.0:
                raise ReverseEngineeringError(f"{name} must be finite and non-negative")


@dataclass(frozen=True)
class StoppingDecision:
    action: str
    reasons: tuple[str, ...]
    digest: str

    @property
    def should_stop(self) -> bool:
        return self.action in {"stop_supported", "stop_futile", "stop_conflicted"}

    def as_dict(self) -> dict[str, Any]:
        return {"action": self.action, "reasons": list(self.reasons), "digest": self.digest}


def evaluate_stopping_rule(
    evidence: StoppingEvidence,
    *,
    rule: StoppingRule = StoppingRule(),
) -> StoppingDecision:
    reasons: list[str] = []
    action = "continue"
    if evidence.contradiction_weight > rule.maximum_contradiction_weight:
        action = "stop_conflicted"
        reasons.append("contradiction_above_limit")
    elif evidence.sample_count >= rule.minimum_samples:
        if (
            evidence.confidence_interval_width is not None
            and evidence.confidence_interval_width <= rule.maximum_confidence_interval_width
        ):
            if (
                evidence.effect_magnitude is not None
                and evidence.effect_magnitude < evidence.minimum_effect_of_interest
            ):
                action = "stop_futile"
                reasons.append("precise_effect_below_minimum_interest")
            elif (
                evidence.effect_magnitude is not None
                and evidence.effect_magnitude >= evidence.minimum_effect_of_interest
                and evidence.replication_ratio is not None
                and evidence.replication_ratio >= rule.minimum_replication_ratio
            ):
                action = "stop_supported"
                reasons.append("precision_effect_and_replication_satisfied")
            else:
                reasons.append("precision_met_but_support_incomplete")
        else:
            reasons.append("precision_not_met")
    else:
        reasons.append("minimum_samples_not_met")
    payload = {
        "evidence": {
            "sample_count": evidence.sample_count,
            "confidence_interval_width": evidence.confidence_interval_width,
            "effect_magnitude": evidence.effect_magnitude,
            "minimum_effect_of_interest": evidence.minimum_effect_of_interest,
            "replication_ratio": evidence.replication_ratio,
            "contradiction_weight": evidence.contradiction_weight,
        },
        "rule": {
            "minimum_samples": rule.minimum_samples,
            "maximum_confidence_interval_width": rule.maximum_confidence_interval_width,
            "minimum_replication_ratio": rule.minimum_replication_ratio,
            "maximum_contradiction_weight": rule.maximum_contradiction_weight,
        },
        "action": action,
    }
    return StoppingDecision(action=action, reasons=tuple(reasons), digest=stable_digest(payload))
