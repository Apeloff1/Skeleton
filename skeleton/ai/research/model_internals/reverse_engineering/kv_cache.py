"""KV-cache scaling characterization from authorized measurements."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class KVCacheObservation:
    observation_id: str
    sequence_length: int
    batch_size: int
    layers: int
    key_heads: int
    value_heads: int
    head_dim: int
    dtype_bytes: float
    observed_bytes: int | None = None

    def __post_init__(self) -> None:
        if not self.observation_id:
            raise ReverseEngineeringError("KV-cache observation requires identity")
        integer_fields = (
            self.sequence_length,
            self.batch_size,
            self.layers,
            self.key_heads,
            self.value_heads,
            self.head_dim,
        )
        if any(value <= 0 for value in integer_fields):
            raise ReverseEngineeringError("KV-cache dimensions must be positive")
        if not isfinite(self.dtype_bytes) or self.dtype_bytes <= 0:
            raise ReverseEngineeringError("dtype_bytes must be finite and positive")
        if self.observed_bytes is not None and self.observed_bytes <= 0:
            raise ReverseEngineeringError("observed_bytes must be positive when present")

    @property
    def theoretical_bytes(self) -> float:
        return (
            self.sequence_length
            * self.batch_size
            * self.layers
            * (self.key_heads + self.value_heads)
            * self.head_dim
            * self.dtype_bytes
        )


@dataclass(frozen=True)
class KVCacheReport:
    observation_count: int
    measured_count: int
    mean_observed_bytes_per_sequence_token: float | None
    coefficient_of_variation: float | None
    approximately_linear: bool | None
    mean_theory_ratio: float | None
    max_relative_theory_error: float | None
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "observation_count": self.observation_count,
            "measured_count": self.measured_count,
            "mean_observed_bytes_per_sequence_token": self.mean_observed_bytes_per_sequence_token,
            "coefficient_of_variation": self.coefficient_of_variation,
            "approximately_linear": self.approximately_linear,
            "mean_theory_ratio": self.mean_theory_ratio,
            "max_relative_theory_error": self.max_relative_theory_error,
            "digest": self.digest,
        }


def analyze_kv_cache(observations: Sequence[KVCacheObservation]) -> KVCacheReport:
    if not observations:
        raise ReverseEngineeringError("KV-cache analysis requires observations")
    ordered = sorted(observations, key=lambda item: item.observation_id)
    measured = [item for item in ordered if item.observed_bytes is not None]
    per_token: list[float] = []
    theory_ratios: list[float] = []
    theory_errors: list[float] = []
    for item in measured:
        assert item.observed_bytes is not None
        per_token.append(item.observed_bytes / (item.sequence_length * item.batch_size))
        theory = item.theoretical_bytes
        theory_ratios.append(item.observed_bytes / theory)
        theory_errors.append(abs(item.observed_bytes - theory) / theory)

    mean_per_token = sum(per_token) / len(per_token) if per_token else None
    cv: float | None = None
    linear: bool | None = None
    if len(per_token) >= 2 and mean_per_token is not None and mean_per_token != 0.0:
        variance = sum((value - mean_per_token) ** 2 for value in per_token) / len(per_token)
        cv = sqrt(variance) / abs(mean_per_token)
        linear = cv <= 0.05

    payload = {
        "observations": [
            {
                "observation_id": item.observation_id,
                "sequence_length": item.sequence_length,
                "batch_size": item.batch_size,
                "layers": item.layers,
                "key_heads": item.key_heads,
                "value_heads": item.value_heads,
                "head_dim": item.head_dim,
                "dtype_bytes": item.dtype_bytes,
                "observed_bytes": item.observed_bytes,
            }
            for item in ordered
        ]
    }
    return KVCacheReport(
        observation_count=len(ordered),
        measured_count=len(measured),
        mean_observed_bytes_per_sequence_token=mean_per_token,
        coefficient_of_variation=cv,
        approximately_linear=linear,
        mean_theory_ratio=(
            sum(theory_ratios) / len(theory_ratios) if theory_ratios else None
        ),
        max_relative_theory_error=max(theory_errors) if theory_errors else None,
        digest=stable_digest(payload),
    )
