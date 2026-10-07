"""Deterministic permutation-null testing for controlled scalar groups."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from random import Random
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class PermutationTestResult:
    control_count: int
    treatment_count: int
    observed_difference: float
    null_mean_absolute_difference: float
    two_sided_p_value: float
    permutations: int
    seed: int
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "control_count": self.control_count,
            "treatment_count": self.treatment_count,
            "observed_difference": self.observed_difference,
            "null_mean_absolute_difference": self.null_mean_absolute_difference,
            "two_sided_p_value": self.two_sided_p_value,
            "permutations": self.permutations,
            "seed": self.seed,
            "digest": self.digest,
        }


def permutation_mean_difference(
    control: Sequence[float],
    treatment: Sequence[float],
    *,
    permutations: int = 2000,
    seed: int = 0,
) -> PermutationTestResult:
    if not control or not treatment:
        raise ReverseEngineeringError("permutation test requires both groups")
    if permutations < 100:
        raise ReverseEngineeringError("permutations must be at least 100")
    combined = [float(value) for value in control] + [float(value) for value in treatment]
    if any(not isfinite(value) for value in combined):
        raise ReverseEngineeringError("permutation values must be finite")

    n_control = len(control)
    observed = (
        sum(float(value) for value in treatment) / len(treatment)
        - sum(float(value) for value in control) / len(control)
    )
    rng = Random(seed)
    absolute_null: list[float] = []
    exceed = 0
    observed_abs = abs(observed)
    for _ in range(permutations):
        shuffled = list(combined)
        rng.shuffle(shuffled)
        perm_control = shuffled[:n_control]
        perm_treatment = shuffled[n_control:]
        difference = (
            sum(perm_treatment) / len(perm_treatment)
            - sum(perm_control) / len(perm_control)
        )
        absolute = abs(difference)
        absolute_null.append(absolute)
        if absolute >= observed_abs - 1e-15:
            exceed += 1

    p_value = (exceed + 1) / (permutations + 1)
    payload = {
        "control": list(map(float, control)),
        "treatment": list(map(float, treatment)),
        "permutations": permutations,
        "seed": seed,
    }
    return PermutationTestResult(
        control_count=len(control),
        treatment_count=len(treatment),
        observed_difference=observed,
        null_mean_absolute_difference=sum(absolute_null) / len(absolute_null),
        two_sided_p_value=p_value,
        permutations=permutations,
        seed=seed,
        digest=stable_digest(payload),
    )
