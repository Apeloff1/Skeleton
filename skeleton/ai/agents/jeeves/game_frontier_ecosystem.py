"""Atmosphere, solar/lunar tide, water mass and sound: game-engine reference models.

830 m means metres above mean sea level (2723.1 ft). Hydrostatic pressure
uses the ISA tropospheric lapse and dry/moist ideal gas mixture. Fog changes
optical visibility, not bulk air density significantly. Cold wind slowdown is
an *optional game design response*, not a meteorological law. Tide harmonics
are fictional/world reference signals, not geographic tide predictions.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from .game_frontier_production import Vec3

RD, RV = 287.05, 461.5
P0, T0, LAPSE, G0 = 101325.0, 288.15, 0.0065, 9.80665
GAMMA = 1.4


class EcosystemError(ValueError):
    pass


def bounded(value: float, name: str, lo: float, hi: float) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not lo <= value <= hi:
        raise EcosystemError(f"{name} must be finite in [{lo}, {hi}]")
    return float(value)


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


@dataclass(frozen=True)
class AirConditions:
    altitude_m: float = 830.0
    temperature_c: float = 15.0
    relative_humidity: float = .5
    fog_liquid_g_m3: float = 0.0
    rain_mm_h: float = 0.0
    particulate_index: float = .3
    cold_wind_damping: float = 0.0

    def __post_init__(self) -> None:
        bounded(self.altitude_m, "altitude_m", -500, 11000)
        bounded(self.temperature_c, "temperature_c", -80, 70)
        bounded(self.relative_humidity, "relative_humidity", 0, 1)
        bounded(self.fog_liquid_g_m3, "fog liquid", 0, 3)
        bounded(self.rain_mm_h, "rain", 0, 1000)
        bounded(self.particulate_index, "particulates", 0, 1)
        bounded(self.cold_wind_damping, "optional cold wind damping", 0, 1)


@dataclass(frozen=True)
class AtmosphereSample:
    altitude_m: float
    altitude_ft: float
    pressure_pa: float
    density_kg_m3: float
    standard_temperature_c: float
    actual_temperature_c: float
    fog_extinction_per_m: float
    meteorological_visibility_m: float
    rain_washed_freshness: float
    effective_wind_factor: float
    sound_speed_m_s: float


def sample_atmosphere(air: AirConditions) -> AtmosphereSample:
    """ISA pressure and wet-air density, fog optical depth, bounded rain washout.

    At equal pressure/temperature, moisture substitutes lower-mass gas, making
    humid air less dense; suspended tiny fog droplets contribute only marginally.
    """
    h = air.altitude_m
    tstd = T0 - LAPSE * h
    p = P0 * (tstd / T0) ** (G0 / (RD * LAPSE))
    tk = air.temperature_c + 273.15
    saturation = 610.94 * math.exp(17.625 * air.temperature_c / (air.temperature_c + 243.04))
    vapor = min(p * .9, air.relative_humidity * saturation)
    rho = (p - vapor) / (RD * tk) + vapor / (RV * tk)
    rho += air.fog_liquid_g_m3 / 1000.0
    extinction = air.fog_liquid_g_m3 * 8.0
    visibility = 3.912 / extinction if extinction > 1e-9 else 100000.0
    visibility = min(100000.0, visibility)
    # This is an explicit game audio/air quality proxy, not a pollutant forecast.
    freshness = clamp(1 - air.particulate_index *
                      math.exp(-min(50.0, air.rain_mm_h / 12)))
    cold = clamp((10 - air.temperature_c) / 60.0)
    wind_factor = 1 - air.cold_wind_damping * cold
    speed = math.sqrt(GAMMA * RD * tk)
    return AtmosphereSample(h, h * 3.280839895, p, rho, tstd - 273.15,
                            air.temperature_c, extinction, visibility,
                            freshness, wind_factor, speed)


@dataclass(frozen=True)
class CelestialCycle:
    time_hours: float
    moon_phase_cycles: float = 0.0
    solar_day_hours: float = 24.0
    lunar_semidiurnal_hours: float = 12.4206
    solar_semidiurnal_hours: float = 12.0
    lunar_amplitude_m: float = 1.0
    solar_amplitude_m: float = .46
    ocean_mean_height_m: float = 0.0

    def __post_init__(self) -> None:
        bounded(self.time_hours, "time_hours", 0, 1e9)
        bounded(self.moon_phase_cycles, "moon_phase", -10000, 10000)
        for key in ("solar_day_hours", "lunar_semidiurnal_hours", "solar_semidiurnal_hours"):
            bounded(getattr(self, key), key, 1, 1000)
        for key in ("lunar_amplitude_m", "solar_amplitude_m"):
            bounded(getattr(self, key), key, 0, 100)
        bounded(self.ocean_mean_height_m, "sea level", -10000, 10000)


@dataclass(frozen=True)
class TideSample:
    water_height_m: float
    rise_rate_m_s: float
    sun_altitude_proxy: float
    moon_phase: float
    tidal_alignment: float
    coastal_current_proxy_m_s: float


def sample_tides(cycle: CelestialCycle) -> TideSample:
    """Two explicit semi-diurnal harmonics with phase, derivative and solar cycle.

    Moon phase aligns solar harmonic at new/full moons (spring tides). At a
    quarter moon, the harmonics partially cancel (neap tides). Astronomical
    forcing is intentionally simplified; coast/bathymetry not modeled.
    """
    lm = 2 * math.pi * cycle.time_hours / cycle.lunar_semidiurnal_hours
    sm = 2 * math.pi * cycle.time_hours / cycle.solar_semidiurnal_hours
    offset = 4 * math.pi * cycle.moon_phase_cycles
    moon = cycle.lunar_amplitude_m * math.cos(lm)
    sun = cycle.solar_amplitude_m * math.cos(sm + offset)
    height = cycle.ocean_mean_height_m + moon + sun
    deriv_per_h = (-cycle.lunar_amplitude_m * 2 * math.pi /
                   cycle.lunar_semidiurnal_hours * math.sin(lm)
                   -cycle.solar_amplitude_m * 2 * math.pi /
                   cycle.solar_semidiurnal_hours * math.sin(sm + offset))
    rise = deriv_per_h / 3600
    alignment = math.cos(4 * math.pi * cycle.moon_phase_cycles)
    daylight = math.sin(2 * math.pi * cycle.time_hours / cycle.solar_day_hours)
    return TideSample(height, rise, daylight,
                      cycle.moon_phase_cycles % 1, alignment,
                      clamp(abs(rise) * 120, 0, 8) *
                      (1 if rise >= 0 else -1))


@dataclass(frozen=True)
class LiquidGrid:
    width: int
    height: int
    cell_size_m: float
    bed_elevation_m: tuple[float, ...]
    water_depth_m: tuple[float, ...]

    def __post_init__(self) -> None:
        if type(self.width) is not int or type(self.height) is not int or not (1 <= self.width <= 64 and 1 <= self.height <= 64):
            raise EcosystemError("grid dimensions require 1..64")
        n = self.width * self.height
        if len(self.bed_elevation_m) != n or len(self.water_depth_m) != n:
            raise EcosystemError("grid cell arrays length mismatch")
        bounded(self.cell_size_m, "cell_size_m", .01, 10000)
        for a in self.bed_elevation_m:
            bounded(a, "bed elevation", -100000, 100000)
        for h in self.water_depth_m:
            bounded(h, "water depth", 0, 10000)

    @property
    def volume_m3(self) -> float:
        return sum(self.water_depth_m) * self.cell_size_m ** 2


@dataclass(frozen=True)
class LiquidStep:
    grid: LiquidGrid
    initial_volume_m3: float
    rain_added_m3: float
    evaporation_removed_m3: float
    final_volume_m3: float
    internal_flux_m3: float
    mass_residual_m3: float


def advance_liquid(grid: LiquidGrid, *, delta_s: float, rain_mm_h: float = 0,
                   evaporation_mm_h: float = 0, flow_rate: float = .4) -> LiquidStep:
    """Conservative four-neighbor shallow-depth flux with donor normalization.

    Boundary is closed unless host explicitly models tide exchange separately.
    Every cell's outgoing transfer is limited to its available water, so long
    steps cannot create negative depth. Not a 3D Navier-Stokes solver.
    """
    dt = bounded(delta_s, "delta_s", 0, 60)
    rain = bounded(rain_mm_h, "rain", 0, 1000) * dt / 3_600_000
    evap = bounded(evaporation_mm_h, "evaporation", 0, 1000) * dt / 3_600_000
    factor = bounded(flow_rate, "flow_rate", 0, 4)
    heights = list(grid.water_depth_m)
    added = removed = 0.0
    for i, depth in enumerate(heights):
        available = depth + rain
        new_depth = max(0, available - evap)
        added += rain
        removed += available - new_depth
        heights[i] = new_depth
    area = grid.cell_size_m ** 2
    potential: list[tuple[int, int, float]] = []
    output = [0.0] * len(heights)
    for y in range(grid.height):
        for x in range(grid.width):
            i = y * grid.width + x
            for nx, ny in ((x + 1, y), (x, y + 1)):
                if nx >= grid.width or ny >= grid.height:
                    continue
                j = ny * grid.width + nx
                head = ((grid.bed_elevation_m[i] + heights[i])
                        - (grid.bed_elevation_m[j] + heights[j]))
                if head == 0:
                    continue
                src, dst = (i, j) if head > 0 else (j, i)
                proposed = min(abs(head) * factor * dt, 1e8)
                output[src] += proposed
                potential.append((src, dst, proposed))
    scale = [min(1., heights[i] / output[i]) if output[i] > 0 else 1.0
             for i in range(len(heights))]
    flux = 0.0
    for src, dst, proposed in potential:
        d = proposed * scale[src]
        heights[src] -= d
        heights[dst] += d
        flux += d * area
    new = LiquidGrid(grid.width, grid.height, grid.cell_size_m,
                     grid.bed_elevation_m, tuple(max(0.0, d) for d in heights))
    first = grid.volume_m3
    residual = new.volume_m3 - (first + (added - removed) * area)
    return LiquidStep(new, first, added * area, removed * area,
                      new.volume_m3, flux, residual)


@dataclass(frozen=True)
class WaterBodyResponse:
    immersion_fraction: float
    buoyant_force_n: float
    drag_force: Vec3
    footstep_splash: float
    wetness_increment: float
    suggested_gait: str


def interact_with_water(*, water_surface_z_m: float, character_foot_z_m: float,
                        character_height_m: float, character_volume_m3: float,
                        velocity: Vec3, flow_velocity: Vec3 = Vec3(0, 0, 0),
                        density_kg_m3: float = 997.0) -> WaterBodyResponse:
    surface = bounded(water_surface_z_m, "water_surface", -10000, 10000)
    foot = bounded(character_foot_z_m, "foot", -10000, 10000)
    height = bounded(character_height_m, "character_height", .05, 10)
    volume = bounded(character_volume_m3, "body_volume", .001, 10)
    density = bounded(density_kg_m3, "liquid density", 100, 2000)
    immersion = clamp((surface - foot) / height)
    buoyancy = density * 9.80665 * volume * immersion
    relative = velocity - flow_velocity
    drag = relative.scaled(-.5 * density * immersion * .65 *
                           math.sqrt(relative.dot(relative)) * .2)
    splash = clamp(immersion * math.sqrt(relative.dot(relative)) / 8)
    gait = "swim" if immersion > .65 else "wade" if immersion > .12 else "walk"
    return WaterBodyResponse(immersion, buoyancy, drag, splash,
                             clamp(immersion * .8), gait)


@dataclass(frozen=True)
class AudioEnvironment:
    source_distance_m: float
    sound_intensity: float
    atmosphere: AtmosphereSample
    weather_rain_mm_h: float
    occluded: bool = False
    tide: TideSample | None = None

    def __post_init__(self) -> None:
        bounded(self.source_distance_m, "audio distance", 0, 100000)
        bounded(self.sound_intensity, "audio intensity", 0, 100000)
        bounded(self.weather_rain_mm_h, "rain", 0, 1000)


@dataclass(frozen=True)
class AudioSynergy:
    delay_s: float
    gain: float
    low_pass_hz: float
    rain_ambience: float
    tide_surf_ambience: float
    cues: tuple[str, ...]


def mix_environment_audio(env: AudioEnvironment) -> AudioSynergy:
    atm, distance = env.atmosphere, env.source_distance_m
    delay = distance / atm.sound_speed_m_s
    gain = env.sound_intensity / (1 + (distance / 8) ** 2)
    gain *= math.exp(-atm.fog_extinction_per_m * distance * .001)
    gain *= .35 if env.occluded else 1.
    cutoff = 20000 / (1 + distance / 200 + env.weather_rain_mm_h / 300)
    surf = (clamp(abs(env.tide.rise_rate_m_s) * 2000)
            if env.tide else 0)
    cues = tuple(k for k, ok in (
        ("rain_on_roof", env.weather_rain_mm_h > 1),
        ("shore_surf", surf > .05),
        ("occluded_sound", env.occluded),
        ("fog_muffled", atm.meteorological_visibility_m < 200),
    ) if ok)
    return AudioSynergy(delay, max(0, gain), cutoff,
                        clamp(env.weather_rain_mm_h / 90), surf, cues)
