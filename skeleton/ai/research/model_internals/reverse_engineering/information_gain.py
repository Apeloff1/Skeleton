"""Information-gain summaries from prior and posterior discrete beliefs."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, log2
from typing import Any, Mapping

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class InformationGainReport:
    hypothesis_count: int
    prior_entropy_bits: float
    posterior_entropy_bits: float
    information_gain_bits: float
    normalized_information_gain: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_count": self.hypothesis_count,
            "prior_entropy_bits": self.prior_entropy_bits,
            "posterior_entropy_bits": self.posterior_entropy_bits,
            "information_gain_bits": self.information_gain_bits,
            "normalized_information_gain": self.normalized_information_gain,
            "digest": self.digest,
        }


def _normalized(distribution: Mapping[str, float]) -> dict[str, float]:
    if not distribution:
        raise ReverseEngineeringError("belief distribution must be non-empty")
    values = {}
    for key, value in distribution.items():
        if not key or not isfinite(value) or value < 0.0:
            raise ReverseEngineeringError("belief probabilities must be finite and non-negative")
        values[key] = float(value)
    total = sum(values.values())
    if total <= 0.0:
        raise ReverseEngineeringError("belief distribution requires positive mass")
    return {key: value / total for key, value in values.items()}


def _entropy(distribution: Mapping[str, float]) -> float:
    return -sum(value * log2(value) for value in distribution.values() if value > 0.0)


def analyze_information_gain(
    prior: Mapping[str, float],
    posterior: Mapping[str, float],
) -> InformationGainReport:
    if set(prior) != set(posterior):
        raise ReverseEngineeringError("prior and posterior hypothesis sets must match")
    p = _normalized(prior)
    q = _normalized(posterior)
    prior_entropy = _entropy(p)
    posterior_entropy = _entropy(q)
    gain = prior_entropy - posterior_entropy
    normalized_gain = gain / prior_entropy if prior_entropy > 0.0 else 0.0
    payload = {
        "prior": {key: p[key] for key in sorted(p)},
        "posterior": {key: q[key] for key in sorted(q)},
    }
    return InformationGainReport(
        hypothesis_count=len(p),
        prior_entropy_bits=prior_entropy,
        posterior_entropy_bits=posterior_entropy,
        information_gain_bits=gain,
        normalized_information_gain=normalized_gain,
        digest=stable_digest(payload),
    )
