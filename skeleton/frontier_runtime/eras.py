"""Per-era fixed-step adaptation taken from the registered engine catalogue.

Eras, tick rates, physics-model names, numeric modes and entity budgets come
from ``skeleton.jeeves.game_engine_lab.list_engine_eras``. This module does
not add an era. The iteration ceiling is the registered entity budget's bit
length, and the contact loop actually stops at that ceiling.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

from skeleton.jeeves.game_engine_lab import (
    EngineEraProfile,
    GameEngineLabError,
    engine_era_profile,
    list_engine_eras,
)


class EraSolverError(ValueError):
    """Raised when a step does not match a registered engine era."""


@dataclass(frozen=True)
class EraSolver:
    era_id: str
    fixed_dt_s: float
    allowed_dt_s: tuple[float, ...]
    iteration_cap: int
    integrator: str
    numeric_mode: str
    tick_hz: int
    entity_budget: int

    def accepts_dt(self, dt: object) -> bool:
        return type(dt) is float and dt in self.allowed_dt_s and dt == dt


def _adapt(profile: EngineEraProfile) -> EraSolver:
    if type(profile.tick_hz) is not int or profile.tick_hz <= 0:
        raise EraSolverError("registered era is missing a positive tick rate")
    if not profile.physics_model or not profile.entity_budget:
        raise EraSolverError("registered era is missing a physics model")
    fixed_dt = 1.0 / profile.tick_hz
    return EraSolver(
        era_id=profile.era.value,
        fixed_dt_s=fixed_dt,
        allowed_dt_s=(fixed_dt,),
        iteration_cap=profile.entity_budget.bit_length(),
        integrator=profile.physics_model,
        numeric_mode=profile.numeric_mode.value,
        tick_hz=profile.tick_hz,
        entity_budget=profile.entity_budget,
    )


def discover_era_solvers() -> tuple[EraSolver, ...]:
    """One solver record for every era ``list_engine_eras`` currently returns."""
    profiles = list_engine_eras()
    if not profiles:
        raise EraSolverError("engine era catalogue is empty")
    solvers = tuple(_adapt(profile) for profile in profiles)
    if len({solver.era_id for solver in solvers}) != len(solvers):
        raise EraSolverError("duplicate engine era id in catalogue")
    return solvers


def era_solver(era: str) -> EraSolver:
    for solver in discover_era_solvers():
        if solver.era_id == era:
            return solver
    catalogue_has_era = True
    try:
        engine_era_profile(era)
    except GameEngineLabError:
        catalogue_has_era = False
    if catalogue_has_era:
        raise EraSolverError(f"registered era {era!r} has no solver adaptation")
    raise EraSolverError(f"no registered engine era {era!r}")


def quantize_scalar(value: float, numeric_mode: str) -> float:
    """Project a solved scalar onto the era's registered numeric mode."""
    number = float(value)
    if numeric_mode == "integer_pixels":
        return float(round(number))
    if numeric_mode == "fixed_8_8":
        return round(number * 256.0) / 256.0
    if numeric_mode == "fixed_16_16":
        return round(number * 65536.0) / 65536.0
    if numeric_mode == "float32":
        return struct.unpack("!f", struct.pack("!f", number))[0]
    if numeric_mode == "float64":
        return number
    raise EraSolverError(f"unknown numeric mode {numeric_mode!r}")


def quantize_vec(xyz: tuple[float, float, float], numeric_mode: str) -> tuple[float, float, float]:
    return tuple(quantize_scalar(component, numeric_mode) for component in xyz)  # type: ignore[return-value]
