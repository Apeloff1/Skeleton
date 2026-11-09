"""Reusable playable simulation loop for mined game mechanics.

Combines terrain, thermals, and glider dynamics behind a deterministic step API.
This is deliberately renderer-neutral so browser, Expo, Godot, bots, and tests
can consume the same simulation state.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from core.flight_dynamics import FlightInput, FlightModel, FlightState
from core.terrain_field import HeightField, Thermal, TerrainConfig, thermal_lift


@dataclass(frozen=True, slots=True)
class SimulationFrame:
    tick: int
    time: float
    state: dict[str, float | bool]
    terrain_height: float
    thermal_lift: float
    clearance: float
    crashed: bool


class PlayableSimulation:
    def __init__(
        self,
        *,
        terrain: HeightField | None = None,
        thermals: Iterable[Thermal] = (),
        model: FlightModel = FlightModel(),
        state: FlightState | None = None,
        crash_clearance: float = 0.5,
    ) -> None:
        if crash_clearance < 0:
            raise ValueError("crash_clearance cannot be negative")
        self.terrain = terrain or HeightField(720.0, 96, config=TerrainConfig())
        self.thermals = tuple(thermals)
        self.model = model
        self.state = state or FlightState()
        self.crash_clearance = crash_clearance
        self.tick = 0
        self.time = 0.0

    def frame(self, lift: float = 0.0) -> SimulationFrame:
        ground = self.terrain.sample(self.state.x, self.state.z)
        clearance = self.state.y - ground
        return SimulationFrame(
            tick=self.tick,
            time=self.time,
            state=asdict(self.state),
            terrain_height=ground,
            thermal_lift=lift,
            clearance=clearance,
            crashed=not self.state.alive,
        )

    def step(self, dt: float, controls: FlightInput = FlightInput()) -> SimulationFrame:
        if dt <= 0:
            raise ValueError("dt must be positive")
        if not self.state.alive:
            return self.frame()
        lift = thermal_lift(
            self.state.x,
            self.state.y,
            self.state.z,
            list(self.thermals),
        )
        self.model.step(self.state, dt, controls, lift)
        self.tick += 1
        self.time += dt
        ground = self.terrain.sample(self.state.x, self.state.z)
        if self.state.y <= ground + self.crash_clearance:
            self.state.y = max(self.state.y, ground)
            self.state.alive = False
        return self.frame(lift)

    def run(
        self,
        *,
        dt: float,
        controls: Iterable[FlightInput],
        max_steps: int | None = None,
    ) -> list[SimulationFrame]:
        frames: list[SimulationFrame] = []
        for idx, action in enumerate(controls):
            if max_steps is not None and idx >= max_steps:
                break
            frame = self.step(dt, action)
            frames.append(frame)
            if frame.crashed:
                break
        return frames
