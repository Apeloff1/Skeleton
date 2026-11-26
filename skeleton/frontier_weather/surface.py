"""Pure weather-to-surface map. It returns values and writes no world."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.jeeves.game_frontier_advanced_physics import TractionSurface
from skeleton.jeeves.game_frontier_ecosystem import AirConditions
from skeleton.jeeves.game_frontier_motion import Weather
from skeleton.jeeves.game_frontier_weather_physics import Microclimate, evolve_microclimate

from skeleton.frontier_weather.contracts import SURFACE_EVAL_DT_S, WeatherPhysicsError


@dataclass(frozen=True)
class SurfaceResponse:
    friction: float
    surface_temperature_c: float
    damage_rate_per_s: float
    authority: str = "derived_surface_response_does_not_write_canonical_world"


def map_weather_to_surface(
    weather: Weather,
    air: AirConditions,
    microclimate: Microclimate,
    traction: TractionSurface,
) -> SurfaceResponse:
    """Map one weather state through the existing microclimate solver.

    ``SURFACE_EVAL_DT_S`` is an evaluation window applied to copies inside
    ``evolve_microclimate``. The same inputs always return the same output.
    Callers keep the canonical world; this function has no world parameter
    and does not assign the evolved surface back onto one.
    """
    if not isinstance(weather, Weather):
        raise WeatherPhysicsError("weather state required")
    if not isinstance(air, AirConditions):
        raise WeatherPhysicsError("air state required")
    if not isinstance(microclimate, Microclimate):
        raise WeatherPhysicsError("microclimate required")
    if not isinstance(traction, TractionSurface):
        raise WeatherPhysicsError("traction surface required")
    evolved = evolve_microclimate(
        microclimate,
        weather,
        air,
        traction,
        delta_s=SURFACE_EVAL_DT_S,
    )
    wetness = evolved.traction_surface.wetness
    ice = evolved.traction_surface.ice_fraction
    friction = evolved.traction_surface.friction_static * (1.0 - 0.55 * wetness) * (1.0 - 0.8 * ice)
    if friction < 0.0:
        friction = 0.0
    elif friction > 3.0:
        friction = 3.0
    damage_rate = evolved.erosion_pressure / SURFACE_EVAL_DT_S
    return SurfaceResponse(
        friction=friction,
        surface_temperature_c=evolved.state.terrain_temperature_c,
        damage_rate_per_s=damage_rate,
    )
