"""Storage-neutral glider flight dynamics mined from Hyperforge cockpit.

The original Three.js craft mixed simulation with rendering. This module keeps
only deterministic motion/flight rules so generated games, tests, bots, and
Godot adapters can share one simulation contract.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True, slots=True)
class FlightInput:
    roll: float = 0.0
    pitch: float = 0.0
    flare: float = 0.0

    def normalized(self) -> "FlightInput":
        return FlightInput(
            clamp(self.roll, -1.0, 1.0),
            clamp(self.pitch, -1.0, 1.0),
            clamp(self.flare, 0.0, 1.0),
        )


@dataclass(slots=True)
class FlightState:
    x: float = 200.0
    y: float = 70.0
    z: float = 0.0
    yaw: float = 0.0
    pitch: float = 0.06
    bank: float = 0.0
    speed: float = 38.0
    alive: bool = True

    def forward(self) -> tuple[float, float, float]:
        cy = math.cos(self.yaw)
        sy = math.sin(self.yaw)
        cp = math.cos(self.pitch)
        sp = math.sin(self.pitch)
        return (-sy * cp, sp, -cy * cp)


@dataclass(frozen=True, slots=True)
class FlightModel:
    max_bank: float = 0.98
    roll_response: float = 10.5
    pitch_rate: float = 1.05
    turn_authority: float = 1.9
    gravity: float = 22.0
    drag: float = 0.0036
    cruise: float = 8.2
    min_speed: float = 12.0
    max_speed: float = 102.0
    thermal_speed_gain: float = 0.38
    thermal_vertical_gain: float = 0.62

    def step(
        self,
        state: FlightState,
        dt: float,
        controls: FlightInput,
        thermal_lift: float = 0.0,
    ) -> FlightState:
        if dt < 0:
            raise ValueError("dt cannot be negative")
        if not state.alive or dt == 0:
            return state
        controls = controls.normalized()
        thermal_lift = max(0.0, thermal_lift)

        roll_target = controls.roll * self.max_bank
        state.bank += (roll_target - state.bank) * (
            1.0 - math.exp(-self.roll_response * dt)
        )

        state.pitch += controls.pitch * self.pitch_rate * dt
        state.pitch = clamp(state.pitch, -0.72, 0.82)
        if abs(controls.pitch) < 0.08:
            state.pitch += (0.07 - state.pitch) * 0.35 * dt

        speed_factor = clamp(state.speed / 42.0, 0.32, 1.85)
        state.yaw += math.sin(state.bank) * self.turn_authority * speed_factor * dt

        gravity_component = -math.sin(state.pitch) * self.gravity
        drag_component = self.drag * state.speed * state.speed
        flare_component = controls.flare * (8.0 + state.speed * 0.35)
        state.speed += (
            self.cruise + gravity_component - drag_component - flare_component
        ) * dt
        state.speed += thermal_lift * self.thermal_speed_gain * dt
        state.speed = clamp(state.speed, self.min_speed, self.max_speed)

        if state.speed < 16.0 and state.pitch > 0.18:
            state.pitch -= 0.85 * dt

        fx, fy, fz = state.forward()
        state.x += fx * state.speed * dt
        state.y += fy * state.speed * dt
        state.z += fz * state.speed * dt
        if thermal_lift > 0:
            state.y += thermal_lift * self.thermal_vertical_gain * dt
        return state

    def simulate(
        self,
        state: FlightState,
        *,
        dt: float,
        steps: int,
        controls: FlightInput,
        thermal_lift: float = 0.0,
    ) -> FlightState:
        if steps < 0:
            raise ValueError("steps cannot be negative")
        for _ in range(steps):
            self.step(state, dt, controls, thermal_lift)
        return state
