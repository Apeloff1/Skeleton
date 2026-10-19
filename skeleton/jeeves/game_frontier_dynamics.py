"""P0-P1 deterministic game-frontier dynamics inside the existing Jeeves game plane.

These are engine-authoritative primitives and candidate-only predictions, not
Genie/LingBot/Cosmos weights or claims of generative video inference. Keep
render cadence independent of gameplay simulation ticks.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math
from typing import Iterable

_NANO = 1_000_000_000
FPS_MODES = frozenset((30, 50, 120))
_SCHEMA = "skeleton.jeeves.frontier_world_dynamics.v1"


class FrontierDynamicsError(ValueError):
    """Invalid wind, cloud, frame, axis, or prediction request."""


def _finite(value: float, name: str, *, limit: float = 1e9) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise FrontierDynamicsError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result) or abs(result) > limit:
        raise FrontierDynamicsError(f"{name} is non-finite or out of bounds")
    return result


def _range(value: float, name: str, lo: float, hi: float) -> float:
    n = _finite(value, name)
    if not lo <= n <= hi:
        raise FrontierDynamicsError(f"{name} must be in [{lo}, {hi}]")
    return n


@dataclass(frozen=True)
class WindVector:
    east_mps: float
    north_mps: float

    def __post_init__(self) -> None:
        _finite(self.east_mps, "east_mps", limit=150)
        _finite(self.north_mps, "north_mps", limit=150)

    def add(self, other: "WindVector") -> "WindVector":
        return WindVector(self.east_mps + other.east_mps,
                          self.north_mps + other.north_mps)

    def scaled(self, factor: float) -> "WindVector":
        return WindVector(self.east_mps * factor, self.north_mps * factor)


@dataclass(frozen=True)
class WindLayer:
    altitude_m: float
    base: WindVector
    turbulence_mps: float = 0.0
    cell_size_m: float = 500.0

    def __post_init__(self) -> None:
        _range(self.altitude_m, "altitude_m", 0, 100000)
        _range(self.turbulence_mps, "turbulence_mps", 0, 30)
        _range(self.cell_size_m, "cell_size_m", 1, 1_000_000)


def _hash_unit(seed: int, x: int, y: int, phase: int, channel: int) -> float:
    digest = sha256(f"{seed}:{x}:{y}:{phase}:{channel}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / (2**64 - 1)


def _smooth(t: float) -> float:
    return t * t * (3 - 2 * t)


def _lattice(seed: int, x: float, y: float, phase: int, channel: int) -> float:
    ix, iy = math.floor(x), math.floor(y)
    tx, ty = _smooth(x - ix), _smooth(y - iy)
    a = _hash_unit(seed, ix, iy, phase, channel)
    b = _hash_unit(seed, ix + 1, iy, phase, channel)
    c = _hash_unit(seed, ix, iy + 1, phase, channel)
    d = _hash_unit(seed, ix + 1, iy + 1, phase, channel)
    return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty


class WindField:
    """Deterministic altitude-aware, time-varying, spatially interpolated wind."""

    def __init__(self, layers: Iterable[WindLayer], *, seed: int = 0,
                 gust_period_s: float = 12.0) -> None:
        self.layers = tuple(sorted(layers, key=lambda layer: layer.altitude_m))
        if not self.layers or len(self.layers) > 32:
            raise FrontierDynamicsError("wind requires 1..32 altitude layers")
        if len({l.altitude_m for l in self.layers}) != len(self.layers):
            raise FrontierDynamicsError("wind altitude layers must be unique")
        if type(seed) is not int or not 0 <= seed < 2**63:
            raise FrontierDynamicsError("invalid wind seed")
        self.seed = seed
        self.gust_period_s = _range(gust_period_s, "gust_period_s", .1, 3600)

    def _at_layer(self, layer: WindLayer, x: float, y: float, time_s: float) -> WindVector:
        period = self.gust_period_s
        p = math.floor(time_s / period)
        t = _smooth((time_s / period) - p)
        cell = layer.cell_size_m
        def channel(c: int) -> float:
            current = _lattice(self.seed, x / cell, y / cell, p, c)
            following = _lattice(self.seed, x / cell, y / cell, p + 1, c)
            return 2 * (current * (1 - t) + following * t) - 1
        return layer.base.add(WindVector(layer.turbulence_mps * channel(0),
                                         layer.turbulence_mps * channel(1)))

    def sample(self, x_m: float, y_m: float, altitude_m: float, time_s: float) -> WindVector:
        x = _finite(x_m, "x_m")
        y = _finite(y_m, "y_m")
        z = _range(altitude_m, "altitude_m", 0, 100000)
        t = _range(time_s, "time_s", 0, 1e9)
        if z <= self.layers[0].altitude_m:
            return self._at_layer(self.layers[0], x, y, t)
        for lower, upper in zip(self.layers, self.layers[1:]):
            if z <= upper.altitude_m:
                weight = (z - lower.altitude_m) / (upper.altitude_m - lower.altitude_m)
                a, b = self._at_layer(lower, x, y, t), self._at_layer(upper, x, y, t)
                return a.scaled(1 - weight).add(b.scaled(weight))
        return self._at_layer(self.layers[-1], x, y, t)


@dataclass(frozen=True)
class Cloud:
    cloud_id: str
    x_m: float
    y_m: float
    altitude_m: float
    opacity: float
    stretch: float = 1.0
    orientation_rad: float = 0.0

    def __post_init__(self) -> None:
        if not self.cloud_id or len(self.cloud_id) > 128:
            raise FrontierDynamicsError("cloud_id required (<=128 characters)")
        _finite(self.x_m, "cloud.x")
        _finite(self.y_m, "cloud.y")
        _range(self.altitude_m, "cloud.altitude", 0, 100000)
        _range(self.opacity, "cloud.opacity", 0, 1)
        _range(self.stretch, "cloud.stretch", .1, 50)
        _finite(self.orientation_rad, "cloud.orientation", limit=1e6)


def advect_clouds(clouds: Iterable[Cloud], wind: WindField, *,
                  time_s: float, elapsed_s: float,
                  wrap_width_m: float | None = None,
                  wrap_height_m: float | None = None) -> tuple[Cloud, ...]:
    """Advect with midpoint integration; shear controls stretch and orientation.

    This modifies cloud placement/shape metadata only. Rendering and geometry
    remain authoritative in the existing engine. Does not invent atmospheric
    ground truth or train a model.
    """
    dt = _range(elapsed_s, "elapsed_s", 0, 3600)
    t = _range(time_s, "time_s", 0, 1e9)
    for n, value in (("wrap_width_m", wrap_width_m), ("wrap_height_m", wrap_height_m)):
        if value is not None:
            _range(value, n, 1, 1e9)
    result: list[Cloud] = []
    for cloud in clouds:
        if not isinstance(cloud, Cloud):
            raise FrontierDynamicsError("expected Cloud")
        a = wind.sample(cloud.x_m, cloud.y_m, cloud.altitude_m, t)
        b = wind.sample(cloud.x_m + a.east_mps * dt / 2,
                        cloud.y_m + a.north_mps * dt / 2,
                        cloud.altitude_m, t + dt / 2)
        upper = wind.sample(cloud.x_m, cloud.y_m,
                            min(100000, cloud.altitude_m + 200), t + dt / 2)
        shear = math.hypot(upper.east_mps - b.east_mps,
                           upper.north_mps - b.north_mps)
        x, y = cloud.x_m + b.east_mps * dt, cloud.y_m + b.north_mps * dt
        if wrap_width_m is not None:
            x %= wrap_width_m
        if wrap_height_m is not None:
            y %= wrap_height_m
        result.append(Cloud(cloud.cloud_id, x, y, cloud.altitude_m,
                            cloud.opacity, min(50, cloud.stretch + dt * shear / 2000),
                            math.atan2(b.north_mps, b.east_mps)
                            if math.hypot(b.east_mps, b.north_mps) > .001
                            else cloud.orientation_rad))
    return tuple(result)


@dataclass(frozen=True)
class FrameSample:
    frame_index: int
    deadline_ns: int
    fps: int


class PresentationClock:
    """Drift-free 30/50/120 FPS presentation schedule; simulation remains separate."""

    def __init__(self, fps: int, *, origin_ns: int = 0) -> None:
        if type(fps) is not int or fps not in FPS_MODES:
            raise FrontierDynamicsError("supported presentation fps: 30, 50, 120")
        if type(origin_ns) is not int or origin_ns < 0:
            raise FrontierDynamicsError("origin_ns must be non-negative integer")
        self.fps, self.origin_ns, self.index = fps, origin_ns, 0

    def deadline(self, index: int) -> int:
        if type(index) is not int or index < 0:
            raise FrontierDynamicsError("frame index must be non-negative")
        return self.origin_ns + (index * _NANO) // self.fps

    def next_frame(self) -> FrameSample:
        value = FrameSample(self.index, self.deadline(self.index), self.fps)
        self.index += 1
        return value

    def due(self, time_ns: int, *, max_frames: int = 8) -> tuple[FrameSample, ...]:
        if type(time_ns) is not int or time_ns < 0:
            raise FrontierDynamicsError("time_ns must be non-negative integer")
        if type(max_frames) is not int or not 1 <= max_frames <= 120:
            raise FrontierDynamicsError("max_frames out of bounds")
        if time_ns < self.origin_ns:
            return ()
        # Drop obsolete presentation frames; do not drop physics simulation ticks.
        newest = (((time_ns - self.origin_ns + 1) * self.fps - 1) // _NANO)
        self.index = max(self.index, newest - max_frames + 1)
        result = []
        while self.index <= newest and len(result) < max_frames:
            result.append(self.next_frame())
        return tuple(result)


@dataclass(frozen=True)
class WorldAxis:
    seed: int
    terrain: float
    moisture: float
    temperature: float
    verticality: float
    sky_islands: float
    weather_volatility: float

    def __post_init__(self) -> None:
        if type(self.seed) is not int or not 0 <= self.seed < 2**63:
            raise FrontierDynamicsError("invalid axis seed")
        for name in ("terrain", "moisture", "temperature", "verticality",
                     "sky_islands", "weather_volatility"):
            _range(getattr(self, name), name, 0, 1)


@dataclass(frozen=True)
class WorldCell:
    x: int
    y: int
    elevation: float
    humidity: float
    temperature: float
    biome: str
    sky_island: bool
    gust_strength: float


def generate_world_cell(axis: WorldAxis, x: int, y: int) -> WorldCell:
    """Smooth seeded multiscale world-axis field, not a Cosmos inference result."""
    if any(type(v) is not int or abs(v) > 10**7 for v in (x, y)):
        raise FrontierDynamicsError("world coordinates invalid")
    def noise(channel: int) -> float:
        return (.58 * _lattice(axis.seed, x / 32, y / 32, 0, channel)
                + .29 * _lattice(axis.seed, x / 8, y / 8, 0, channel)
                + .13 * _lattice(axis.seed, x / 2, y / 2, 0, channel))
    elevation = min(1, max(0, .5 * noise(0) + .5 * axis.terrain))
    humid = min(1, max(0, .6 * noise(1) + .4 * axis.moisture))
    temp = min(1, max(0, .6 * noise(2) + .4 * axis.temperature - .12 * elevation))
    biome = ("snow" if temp < .28 else "desert" if humid < .28
             else "marsh" if humid > .72 else "mountain" if elevation > .72
             else "woodland" if humid > .5 else "grassland")
    islands = noise(3) + axis.sky_islands * .5 + axis.verticality * .2 > 1.13
    return WorldCell(x, y, elevation, humid, temp, biome, islands,
                     axis.weather_volatility * (.5 + .5 * noise(4)))


@dataclass(frozen=True)
class InputObservation:
    at_ns: int
    user_x: float
    user_y: float
    velocity_x: float
    velocity_y: float
    source_digest: str

    def __post_init__(self) -> None:
        if type(self.at_ns) is not int or self.at_ns < 0:
            raise FrontierDynamicsError("invalid observation timestamp")
        for k in ("user_x", "user_y", "velocity_x", "velocity_y"):
            _finite(getattr(self, k), k, limit=1e6)
        if len(self.source_digest) != 64 or any(c not in "0123456789abcdef" for c in self.source_digest):
            raise FrontierDynamicsError("source_digest must be SHA-256")


@dataclass(frozen=True)
class AnticipatedPosition:
    x: float
    y: float
    prediction_horizon_ms: int
    confidence_upper_bound: float
    source_digest: str
    authority: str = "speculative_never_auto_execute"


def anticipate_user_motion(observation: InputObservation, *, horizon_ms: int,
                           max_speed_mps: float = 40) -> AnticipatedPosition:
    """WHAM-inspired speculative lookahead, without firing controls or a model."""
    if type(horizon_ms) is not int or not 0 <= horizon_ms <= 500:
        raise FrontierDynamicsError("prediction horizon must be 0..500ms")
    speed = _range(max_speed_mps, "max_speed_mps", .01, 1000)
    vx = max(-speed, min(speed, observation.velocity_x))
    vy = max(-speed, min(speed, observation.velocity_y))
    t = horizon_ms / 1000
    uncertainty = min(1, t * (math.hypot(vx, vy) / speed + .2))
    return AnticipatedPosition(observation.user_x + vx * t,
                               observation.user_y + vy * t,
                               horizon_ms, 1 - uncertainty,
                               observation.source_digest)
