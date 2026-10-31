"""Microclimate coupling for existing wind, characters, terrain, and climbing.

Uses explicit physical units and bounded heat/rain/wind approximations.
Weather inputs derive local wet/ice/erosion state, pressure-gradient wind
and convective uplift. Native weather CFD, ice accretion and structural
fracture remain outside this CPU reference.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import math

from .game_frontier_production import Vec3
from .game_frontier_ecosystem import AirConditions, sample_atmosphere
from .game_frontier_motion import Weather
from .game_frontier_advanced_physics import TractionSurface, UpdraftColumn


class WeatherCouplingError(ValueError):
    pass


def scalar(value: float, label: str, lo: float, hi: float) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not lo <= value <= hi:
        raise WeatherCouplingError(f"{label} outside physical reference envelope")
    return float(value)


def cap(value: float, lo: float = 0., hi: float = 1.) -> float:
    return min(hi, max(lo, value))


@dataclass(frozen=True)
class Microclimate:
    terrain_temperature_c: float
    soil_water_fraction: float
    ground_ice_fraction: float
    loose_sediment_fraction: float
    surface_roughness: float
    vegetation_cover: float
    pressure_gradient_pa_m: Vec3 = Vec3(0, 0, 0)
    ground_heat_flux_w_m2: float = 0.
    convection_radius_m: float = 12.
    convection_height_m: float = 120.

    def __post_init__(self) -> None:
        scalar(self.terrain_temperature_c, "terrain temp", -120, 120)
        for name in ("soil_water_fraction","ground_ice_fraction",
                     "loose_sediment_fraction","surface_roughness",
                     "vegetation_cover"):
            scalar(getattr(self,name), name, 0, 1)
        for name in ("x","y","z"):
            scalar(getattr(self.pressure_gradient_pa_m,name),
                   "pressure gradient", -20, 20)
        scalar(self.ground_heat_flux_w_m2, "ground heat flux", -2000, 3000)
        scalar(self.convection_radius_m,"thermal radius",1,10000)
        scalar(self.convection_height_m,"thermal height",1,100000)


@dataclass(frozen=True)
class WeatherTerrainStep:
    state: Microclimate
    traction_surface: TractionSurface
    pressure_wind_delta: Vec3
    terrain_updraft: UpdraftColumn
    rain_absorption_m: float
    evaporation_m: float
    freeze_thaw_transition: float
    erosion_pressure: float
    air_density_kg_m3: float
    ground_air_temperature_gradient_c: float
    authority: str = "candidate_local_microclimate_not_weather_forecast"


def evolve_microclimate(
    micro: Microclimate, weather: Weather, air: AirConditions,
    traction: TractionSurface, *,
    delta_s: float,
    location: Vec3 = Vec3(0,0,0),
) -> WeatherTerrainStep:
    """Couple rainfall, thaw, thermal uplift, pressure shear and ground grip.

    Substeps are limited to 60 s: long world-time fast-forward must use the
    existing durable scheduler/checkpoints, not skip nonlinear freeze-thaw.
    """
    dt = scalar(delta_s, "weather dt", 0, 60)
    density = sample_atmosphere(air).density_kg_m3
    # Rain mass volume per horizontal m2; runoff saturates beyond pore capacity.
    rain_m = weather.precipitation_mm_h / 3_600_000 * dt
    freezing = cap(-weather.temperature_c / 20)
    melting = cap(weather.temperature_c / 20)
    ice_gain = min(1 - micro.ground_ice_fraction,
                   rain_m * 25 * freezing + micro.soil_water_fraction * freezing * dt * .0004)
    ice_loss = micro.ground_ice_fraction * melting * dt * .0006
    ice = cap(micro.ground_ice_fraction + ice_gain - ice_loss)
    solar_dry = cap(weather.sunlight) * max(0,weather.temperature_c) * dt * .000003
    wind_dry = math.hypot(weather.wind.x,weather.wind.y) * dt * .0000009
    evaporation = min(micro.soil_water_fraction,solar_dry+wind_dry)
    wet = cap(micro.soil_water_fraction + rain_m*15 - evaporation
              - max(0,ice_gain) * .3 + ice_loss * .8)
    # Soil loosens from runoff and freeze/thaw, and compacts under vegetation.
    sediment = cap(micro.loose_sediment_fraction + rain_m * 7 +
                   (ice_gain+ice_loss)*.04 - dt*.000003*micro.vegetation_cover)
    heat_target = weather.temperature_c + micro.ground_heat_flux_w_m2*.006
    temp = micro.terrain_temperature_c + (
        heat_target-micro.terrain_temperature_c) * min(1, dt / 900)
    gradient = temp - air.temperature_c
    # Bulk heat-buoyancy reference m/s, a finite convection proxy.
    buoyant = math.copysign(
        min(20., math.sqrt(2*9.80665*micro.convection_height_m*
                           abs(gradient)/(273.15+max(-80,air.temperature_c)))
            * .12), gradient) if abs(gradient) > .01 else 0.
    # Horizontal pressure-gradient acceleration (Pa/m / kg/m3), with a
    # conservative finite-time response, independent of wind friction.
    pressure = micro.pressure_gradient_pa_m.scaled(-dt/max(.01,density))
    strength = math.sqrt(pressure.dot(pressure))
    if strength > 20:
        pressure = pressure.scaled(20/strength)
    rough = cap(micro.surface_roughness+.4*micro.vegetation_cover)
    pressure = pressure.scaled(1-.65*rough)
    updraft = UpdraftColumn(location, micro.convection_radius_m,
                            buoyant, micro.convection_height_m)
    new = replace(micro,terrain_temperature_c=temp,
                  soil_water_fraction=wet, ground_ice_fraction=ice,
                  loose_sediment_fraction=sediment)
    surface = replace(traction,
                      wetness=max(traction.wetness,wet),
                      ice_fraction=max(traction.ice_fraction,ice),
                      loose_gravel=max(traction.loose_gravel,sediment))
    erosion = cap(rain_m * 100 * (1-micro.vegetation_cover)
                  * (1+.5*sediment))
    return WeatherTerrainStep(
        new,surface,pressure,updraft,rain_m,evaporation,
        ice_gain-ice_loss,erosion,density,gradient,
    )
