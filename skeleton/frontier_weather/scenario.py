"""Stable inputs for the marathon weather slice. These are data, not a second solver."""

from __future__ import annotations

import math

from skeleton.jeeves.game_frontier_advanced_physics import TractionSurface
from skeleton.jeeves.game_frontier_ecosystem import AirConditions, LiquidGrid
from skeleton.jeeves.game_frontier_motion import Weather
from skeleton.jeeves.game_frontier_production import Vec3
from skeleton.jeeves.game_frontier_weather_physics import Microclimate

from skeleton.frontier_weather.clock import DragParticle, MarathonState
from skeleton.frontier_weather.contracts import FIXED_SEED
from skeleton.frontier_weather.wind import BoundaryLayerSpec, build_boundary_layer


def ridge_terrain(nx: int, ny: int, cell_size_m: float) -> tuple[float, ...]:
    """A single ridge whose highest cell is the center column and row."""
    crest_i = nx // 2
    crest_j = ny // 2
    heights: list[float] = []
    for j in range(ny):
        for i in range(nx):
            di = (i - crest_i) * cell_size_m
            dj = (j - crest_j) * cell_size_m
            ridge = math.exp(-(di * di) / (2.0 * 60.0 * 60.0))
            spine = math.exp(-(dj * dj) / (2.0 * 70.0 * 70.0))
            heights.append(12.0 * ridge * (0.75 + 0.25 * spine))
    return tuple(heights)


def reference_boundary_spec() -> BoundaryLayerSpec:
    nx = 8
    ny = 8
    cell = 25.0
    return BoundaryLayerSpec(
        nx=nx,
        ny=ny,
        cell_size_m=cell,
        viscosity_m2_s=5.0,
        roughness_m=0.2,
        friction_velocity_m_s=0.3,
        z_ref_m=12.0,
        slab_thickness_m=12.0,
        direction_x=1.0,
        direction_y=0.0,
        terrain_m=ridge_terrain(nx, ny, cell),
        speedup_gain=1.0,
        speedup_length_m=100.0,
        circulation_gain=0.8,
        core_radius_m=40.0,
        shed_distance_m=50.0,
        air=AirConditions(),
        seed=FIXED_SEED,
    )


def reference_droplets() -> LiquidGrid:
    width = 4
    height = 4
    bed: list[float] = []
    depth: list[float] = []
    for y in range(height):
        for x in range(width):
            bed.append(0.05 * x + 0.02 * y)
            depth.append(0.25)
    return LiquidGrid(width, height, 2.0, tuple(bed), tuple(depth))


def reference_marathon_state() -> MarathonState:
    spec = reference_boundary_spec()
    field = build_boundary_layer(spec)
    weather = Weather(
        Vec3(field.log_speed_m_s, 0.0, 0.0),
        12.0,
        precipitation_mm_h=0.0,
        humidity=0.5,
        sunlight=0.8,
    )
    particle = DragParticle(
        role="foliage_fabric",
        mass_kg=0.4,
        position=Vec3(2.5 * spec.cell_size_m, 3.5 * spec.cell_size_m, 2.0),
        velocity=Vec3(0.0, 0.0, 0.0),
        drag_coefficient=0.85,
        area_m2=0.4,
        radius_m=0.15,
    )
    microclimate = Microclimate(
        terrain_temperature_c=8.0,
        soil_water_fraction=0.1,
        ground_ice_fraction=0.0,
        loose_sediment_fraction=0.1,
        surface_roughness=0.6,
        vegetation_cover=0.3,
    )
    traction = TractionSurface(Vec3(0.0, 0.0, 1.0), 1.0, 0.75)
    return MarathonState(
        wind=field,
        particle=particle,
        droplets=reference_droplets(),
        air=spec.air,
        weather=weather,
        microclimate=microclimate,
        traction=traction,
        step_index=0,
        seed=spec.seed,
    )
