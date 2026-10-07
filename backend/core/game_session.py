"""Integrated playable game session composed from mined runtime primitives.

Bridges renderer-neutral flight simulation, ordered course checkpoints, ghost
telemetry, and progression-ready finish output. This is the first end-to-end
runtime object suitable for Play pillar adapters.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from core.course_runtime import Course, CourseTracker
from core.flight_dynamics import FlightInput, FlightState
from core.playable_simulation import PlayableSimulation, SimulationFrame
from core.progression import Medal
from core.terrain_field import HeightField


_MEDAL_MAP = {
    "none": Medal.NONE,
    "bronze": Medal.BRONZE,
    "silver": Medal.SILVER,
    "gold": Medal.GOLD,
    "elite": Medal.ELITE,
}


@dataclass(frozen=True, slots=True)
class GhostSample:
    t: float
    x: float
    y: float
    z: float
    yaw: float
    pitch: float
    bank: float
    speed: float


@dataclass(frozen=True, slots=True)
class GameStep:
    frame: SimulationFrame
    next_ring: int
    finished: bool
    medal: Medal


class GameSession:
    def __init__(
        self,
        course: Course,
        *,
        terrain: HeightField,
        state: FlightState | None = None,
        ghost_sample_interval: float = 0.1,
    ) -> None:
        if ghost_sample_interval <= 0:
            raise ValueError("ghost_sample_interval must be positive")
        spawn_state = state or FlightState(
            x=course.start.x,
            y=course.start.y,
            z=course.start.z,
            yaw=course.start.yaw,
        )
        self.course = course
        self.simulation = PlayableSimulation(
            terrain=terrain,
            thermals=course.thermals,
            state=spawn_state,
        )
        self.tracker = CourseTracker(course)
        self.ghost_sample_interval = ghost_sample_interval
        self._ghost: list[GhostSample] = []
        self._next_sample_at = 0.0
        self._distance = 0.0
        self._last_position = (spawn_state.x, spawn_state.y, spawn_state.z)
        self._sample(force=True)

    @property
    def distance(self) -> float:
        return self._distance

    @property
    def ghost(self) -> tuple[GhostSample, ...]:
        return tuple(self._ghost)

    def _sample(self, *, force: bool = False) -> None:
        if not force and self.simulation.time + 1e-9 < self._next_sample_at:
            return
        state = self.simulation.state
        self._ghost.append(
            GhostSample(
                t=self.simulation.time,
                x=state.x,
                y=state.y,
                z=state.z,
                yaw=state.yaw,
                pitch=state.pitch,
                bank=state.bank,
                speed=state.speed,
            )
        )
        self._next_sample_at = self.simulation.time + self.ghost_sample_interval

    def step(self, dt: float, controls: FlightInput = FlightInput()) -> GameStep:
        previous = self._last_position
        frame = self.simulation.step(dt, controls)
        current = (
            self.simulation.state.x,
            self.simulation.state.y,
            self.simulation.state.z,
        )
        dx = current[0] - previous[0]
        dy = current[1] - previous[1]
        dz = current[2] - previous[2]
        self._distance += (dx * dx + dy * dy + dz * dz) ** 0.5
        self._last_position = current
        progress = self.tracker.step(dt, previous, current)
        self._sample()
        return GameStep(
            frame=frame,
            next_ring=progress.next_ring,
            finished=progress.finished,
            medal=_MEDAL_MAP[self.tracker.medal_band()],
        )

    def finish_payload(self) -> dict[str, Any]:
        progress = self.tracker.progress
        return {
            "course_id": self.course.id,
            "finished": progress.finished,
            "elapsed": progress.elapsed,
            "completed_rings": progress.completed_rings,
            "total_rings": len(self.course.rings),
            "medal": int(_MEDAL_MAP[self.tracker.medal_band()]),
            "distance": self._distance,
            "ghost": [asdict(sample) for sample in self._ghost],
        }
