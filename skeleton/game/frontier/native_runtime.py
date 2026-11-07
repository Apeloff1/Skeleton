"""Integrate frontier weather, 30/50/60/120 FPS presentation and LOD (#4167).

Authority split (extend-only, no existing module is changed):

* Physics/weather ticks: canonical ``FixedTimestep`` from
  ``skeleton.game.simulation``. Weather (``WindField`` + ``advect_clouds``)
  and entity motion advance only inside simulation ticks.
* Presentation: ``PresentationClock`` (30/50/60/120) decides when a render
  frame is produced. It never changes ``step_ns`` and never adds or drops a
  physics tick, so the simulation digest is identical for every FPS tier.
* LOD: canonical ``LODPolicy`` from ``skeleton.game.render`` selects a level
  per entity per presented frame from the camera distance (integer mm).

This is a deterministic CPU runtime loop. It does not claim GPU framebuffer
rates, Godot playback or device acceptance; those remain open in #4167.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
import math
from typing import Iterable, Sequence

from skeleton.ai.agents.jeeves.game_frontier_dynamics import (
    FPS_MODES, Cloud, PresentationClock, WindField, advect_clouds,
)
from skeleton.game.render.flgb_render_runtime import LODPolicy
from skeleton.game.simulation.flgb_simulation_runtime import FixedTimestep

_NANO = 1_000_000_000
SCHEMA = "skeleton.game.frontier.native_runtime.v1"
MAX_ENTITIES = 4096
MAX_CLOUDS = 1024


class FrontierRuntimeError(ValueError):
    pass


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode()).hexdigest()


def _q(value: float) -> int:
    """Quantise metres to integer micrometres for platform-stable digests."""
    return int(round(value * 1_000_000))


@dataclass(frozen=True)
class FrontierEntity:
    entity_id: str
    x_m: float
    y_m: float
    z_m: float
    vx_mps: float = 0.0
    vy_mps: float = 0.0
    wind_coupling: float = 0.0  # 0 = ignores wind, 1 = moves with the wind

    def __post_init__(self) -> None:
        if not isinstance(self.entity_id, str) or not 0 < len(self.entity_id) <= 128:
            raise FrontierRuntimeError("entity_id required (<=128 chars)")
        for name in ("x_m", "y_m", "z_m", "vx_mps", "vy_mps", "wind_coupling"):
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                raise FrontierRuntimeError(f"{name} must be finite")
        if not 0.0 <= self.wind_coupling <= 1.0:
            raise FrontierRuntimeError("wind_coupling must be in 0..1")
        if not 0.0 <= self.z_m <= 100000:
            raise FrontierRuntimeError("z_m must be in 0..100000")


@dataclass(frozen=True)
class FrontierFrame:
    frame_index: int
    deadline_ns: int
    fps: int
    simulation_tick: int
    interpolation_alpha: float
    lod_levels: tuple[tuple[str, int], ...]
    cloud_positions_m: tuple[tuple[str, float, float], ...]
    simulation_digest: str
    frame_digest: str


class FrontierNativeRuntime:
    """One loop: fixed physics/weather ticks, decoupled presentation, LOD."""

    def __init__(self, *, fps: int, wind: WindField, lod: LODPolicy,
                 entities: Sequence[FrontierEntity] = (),
                 clouds: Iterable[Cloud] = (), simulation_hz: int = 50,
                 camera_m: tuple[float, float, float] = (0.0, 0.0, 0.0),
                 max_catchup_ticks: int = 8,
                 wrap_m: tuple[float, float] | None = None) -> None:
        if type(fps) is not int or fps not in FPS_MODES:
            raise FrontierRuntimeError("fps must be 30, 50, 60 or 120")
        if type(simulation_hz) is not int or not 1 <= simulation_hz <= 1000 \
                or _NANO % simulation_hz:
            raise FrontierRuntimeError(
                "simulation_hz must divide 1e9 exactly (drift-free integer step)")
        if not isinstance(wind, WindField) or not isinstance(lod, LODPolicy):
            raise FrontierRuntimeError("wind must be WindField and lod LODPolicy")
        ents = tuple(entities)
        if len(ents) > MAX_ENTITIES or len({e.entity_id for e in ents}) != len(ents):
            raise FrontierRuntimeError("entities must be unique and bounded")
        cl = tuple(clouds)
        if len(cl) > MAX_CLOUDS or len({c.cloud_id for c in cl}) != len(cl):
            raise FrontierRuntimeError("clouds must be unique and bounded")
        self.fps, self.simulation_hz = fps, simulation_hz
        self.timestep = FixedTimestep(_NANO // simulation_hz, max_catchup_ticks)
        self.presentation = PresentationClock(fps)
        self.wind, self.lod, self.wrap = wind, lod, wrap_m
        self.camera = tuple(float(c) for c in camera_m)
        self.entities, self.clouds = ents, cl
        self._prev_clouds = cl
        self.tick = 0
        self.accumulator_ns = 0
        self.time_ns = 0
        self.dropped_catchup_ns = 0

    # -- simulation authority ------------------------------------------------
    def _simulate_tick(self) -> None:
        dt = self.timestep.step_ns / _NANO
        t = self.tick * dt
        self._prev_clouds = self.clouds
        kw = {}
        if self.wrap is not None:
            kw = {"wrap_width_m": self.wrap[0], "wrap_height_m": self.wrap[1]}
        self.clouds = advect_clouds(self.clouds, self.wind, time_s=t,
                                    elapsed_s=dt, **kw)
        moved = []
        for e in self.entities:
            w = self.wind.sample(e.x_m, e.y_m, e.z_m, t)
            vx = e.vx_mps + e.wind_coupling * w.east_mps
            vy = e.vy_mps + e.wind_coupling * w.north_mps
            moved.append(replace(e, x_m=e.x_m + vx * dt, y_m=e.y_m + vy * dt))
        self.entities = tuple(moved)
        self.tick += 1

    def simulation_digest(self) -> str:
        return _digest({
            "schema": SCHEMA, "tick": self.tick, "step_ns": self.timestep.step_ns,
            "entities": [[e.entity_id, _q(e.x_m), _q(e.y_m), _q(e.z_m)]
                         for e in self.entities],
            "clouds": [[c.cloud_id, _q(c.x_m), _q(c.y_m), _q(c.stretch),
                        _q(c.orientation_rad)] for c in self.clouds],
        })

    def advance_to(self, time_ns: int) -> int:
        """Run every physics tick due by ``time_ns``. Returns ticks run."""
        if type(time_ns) is not int or time_ns < self.time_ns:
            raise FrontierRuntimeError("time_ns must be a non-decreasing int")
        ticks, acc = self.timestep.consume(self.accumulator_ns,
                                           time_ns - self.time_ns)
        # FixedTimestep caps catch-up; the remainder past the cap is real
        # lost time and is recorded rather than silently re-simulated.
        if acc >= self.timestep.step_ns:
            lost = acc - acc % self.timestep.step_ns
            self.dropped_catchup_ns += lost
            acc -= lost
        for _ in range(ticks):
            self._simulate_tick()
        self.accumulator_ns, self.time_ns = acc, time_ns
        return ticks

    # -- presentation + LOD --------------------------------------------------
    def _distance_mm(self, x: float, y: float, z: float) -> int:
        cx, cy, cz = self.camera
        return int(math.hypot(x - cx, y - cy, z - cz) * 1000)

    def present_next(self) -> FrontierFrame:
        sample = self.presentation.next_frame()
        # A frame is presented at the end of its interval, so frame n shows
        # the simulation state at deadline(n + 1): N frames span N/fps s.
        deadline = self.presentation.deadline(sample.frame_index + 1)
        self.advance_to(deadline)
        alpha = self.accumulator_ns / self.timestep.step_ns
        lods = tuple((e.entity_id,
                      self.lod.choose(self._distance_mm(e.x_m, e.y_m, e.z_m)).level)
                     for e in self.entities)
        prev = {c.cloud_id: c for c in self._prev_clouds}
        clouds = []
        for c in self.clouds:
            p = prev.get(c.cloud_id, c)
            dx, dy = c.x_m - p.x_m, c.y_m - p.y_m
            if self.wrap is not None and (abs(dx) > self.wrap[0] / 2
                                          or abs(dy) > self.wrap[1] / 2):
                p = c  # wrapped this tick; do not interpolate across the seam
            clouds.append((c.cloud_id, p.x_m + (c.x_m - p.x_m) * alpha,
                           p.y_m + (c.y_m - p.y_m) * alpha))
        sim = self.simulation_digest()
        frame_digest = _digest({
            "fps": self.fps, "frame": sample.frame_index,
            "deadline_ns": deadline, "sim": sim,
            "alpha_ppm": int(alpha * 1_000_000), "lod": list(lods),
            "clouds": [[i, _q(x), _q(y)] for i, x, y in clouds],
        })
        return FrontierFrame(sample.frame_index, deadline, self.fps,
                             self.tick, alpha, lods, tuple(clouds), sim,
                             frame_digest)

    def run_seconds(self, seconds: int) -> list[FrontierFrame]:
        if type(seconds) is not int or not 1 <= seconds <= 600:
            raise FrontierRuntimeError("seconds must be int in 1..600")
        return [self.present_next() for _ in range(self.fps * seconds)]


def prove_presentation_tiers(factory, *, seconds: int = 2) -> dict:
    """Run the same scene at 30/50/60/120 FPS and compare physics outcomes.

    ``factory(fps)`` must build a fresh ``FrontierNativeRuntime``. Proves the
    presented frame count matches each tier exactly and the simulation tick
    count and state digest are identical (physics ticks not modified).
    CPU-loop evidence only, not a GPU render-rate measurement.
    """
    modes = {}
    for fps in sorted(FPS_MODES):
        rt = factory(fps)
        if not isinstance(rt, FrontierNativeRuntime) or rt.fps != fps:
            raise FrontierRuntimeError("factory must return runtime at requested fps")
        frames = rt.run_seconds(seconds)
        modes[fps] = {
            "frames": len(frames),
            "last_deadline_ns": frames[-1].deadline_ns,
            "simulation_ticks": rt.tick,
            "simulation_digest": rt.simulation_digest(),
            "dropped_catchup_ns": rt.dropped_catchup_ns,
        }
    return {
        "schema": SCHEMA, "seconds": seconds, "modes": modes,
        "frames_exact": all(m["frames"] == f * seconds for f, m in modes.items()),
        "deadlines_drift_free": all(m["last_deadline_ns"] == seconds * _NANO
                                    for m in modes.values()),
        "physics_identical": len({(m["simulation_ticks"], m["simulation_digest"])
                                  for m in modes.values()}) == 1,
        "claim": "cpu_runtime_loop_not_gpu_framebuffer",
    }
