"""Closed-form experiment power planning for standardized effects."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isfinite
from statistics import NormalDist
from typing import Any

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class PowerPlan:
    standardized_effect: float
    alpha: float
    target_power: float
    two_sided: bool
    samples_per_group: int
    total_samples: int
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "standardized_effect": self.standardized_effect,
            "alpha": self.alpha,
            "target_power": self.target_power,
            "two_sided": self.two_sided,
            "samples_per_group": self.samples_per_group,
            "total_samples": self.total_samples,
            "digest": self.digest,
        }


def plan_two_group_power(
    standardized_effect: float,
    *,
    alpha: float = 0.05,
    target_power: float = 0.8,
    two_sided: bool = True,
) -> PowerPlan:
    effect = abs(float(standardized_effect))
    if not isfinite(effect) or effect <= 0.0:
        raise ReverseEngineeringError("standardized_effect must be finite and non-zero")
    if not isfinite(alpha) or not 0.0 < alpha < 1.0:
        raise ReverseEngineeringError("alpha must be within (0, 1)")
    if not isfinite(target_power) or not 0.0 < target_power < 1.0:
        raise ReverseEngineeringError("target_power must be within (0, 1)")

    normal = NormalDist()
    alpha_tail = alpha / 2.0 if two_sided else alpha
    z_alpha = normal.inv_cdf(1.0 - alpha_tail)
    z_power = normal.inv_cdf(target_power)
    per_group = max(2, ceil(2.0 * ((z_alpha + z_power) / effect) ** 2))
    payload = {
        "standardized_effect": effect,
        "alpha": alpha,
        "target_power": target_power,
        "two_sided": two_sided,
        "samples_per_group": per_group,
    }
    return PowerPlan(
        standardized_effect=effect,
        alpha=alpha,
        target_power=target_power,
        two_sided=two_sided,
        samples_per_group=per_group,
        total_samples=per_group * 2,
        digest=stable_digest(payload),
    )
