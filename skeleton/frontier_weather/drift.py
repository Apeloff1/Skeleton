"""Long-horizon kinetic-energy drift against an independent reference series."""

from __future__ import annotations

import math
from dataclasses import dataclass

from skeleton.frontier_weather.contracts import (
    ENERGY_DRIFT_BOUND,
    MIN_HORIZON_STEPS,
    SCHEME,
    EnergyDriftError,
    canonical_json,
)


@dataclass(frozen=True)
class DriftReceipt:
    steps: int
    seed: int
    max_relative_drift: float
    bound: float
    worst_step: int
    canonical: str


def enforce_energy_drift(
    solver_kinetic_energy_j: tuple[float, ...] | list[float],
    reference_kinetic_energy_j: tuple[float, ...] | list[float],
    *,
    seed: int,
) -> DriftReceipt:
    """Fail the run when relative drift exceeds the documented bound.

    Both series are post-step kinetic energies. The reference is supplied by
    the caller (the test's finite-difference integrator). Fewer than
    ``MIN_HORIZON_STEPS`` samples is a failed run, not a skipped check.
    """
    if type(seed) is not int or seed < 0 or seed >= 2**63:
        raise EnergyDriftError("seed must be the fixed non-negative integer stored with the run")
    solver = list(solver_kinetic_energy_j)
    reference = list(reference_kinetic_energy_j)
    if len(solver) < MIN_HORIZON_STEPS or len(reference) != len(solver):
        raise EnergyDriftError(
            f"long-horizon drift requires matching series of at least {MIN_HORIZON_STEPS} steps"
        )
    worst = 0.0
    worst_step = 0
    for index, (solver_ke, reference_ke) in enumerate(zip(solver, reference), start=1):
        if (
            type(solver_ke) not in (int, float)
            or type(reference_ke) not in (int, float)
            or not math.isfinite(solver_ke)
            or not math.isfinite(reference_ke)
        ):
            raise EnergyDriftError("non-finite kinetic energy fails the drift run")
        scale = abs(reference_ke) if abs(reference_ke) > 1e-30 else 1e-30
        relative = abs(float(solver_ke) - float(reference_ke)) / scale
        if relative > worst:
            worst = relative
            worst_step = index
    if worst > ENERGY_DRIFT_BOUND:
        raise EnergyDriftError(
            f"energy drift {worst} exceeds documented bound {ENERGY_DRIFT_BOUND} at step {worst_step}"
        )
    payload = {
        "bound": ENERGY_DRIFT_BOUND,
        "max_relative_drift": worst,
        "passed": True,
        "scheme": SCHEME,
        "seed": seed,
        "steps": len(solver),
        "worst_step": worst_step,
    }
    return DriftReceipt(
        steps=len(solver),
        seed=seed,
        max_relative_drift=worst,
        bound=ENERGY_DRIFT_BOUND,
        worst_step=worst_step,
        canonical=canonical_json(payload),
    )
