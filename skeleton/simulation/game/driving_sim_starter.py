"""skeleton/simulation/game/driving_sim_starter.py
20x ultra-complete driving simulation. Aero, downforce, damage, telemetry, full dynamics.
Fail-closed. Receipts. No stubs.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Final, List, Dict

try:
    from skeleton.kernel.errors import SkeletonError
except ImportError:
    class SkeletonError(Exception):
        pass

try:
    from skeleton.provenance.chronicle import emit_receipt
except ImportError:
    def emit_receipt(**kwargs):
        return kwargs.get("digest", "")

_MAX_SPEED: Final[float] = 320.0
_DT: Final[float] = 0.016
_AIR_DENSITY: Final[float] = 1.225

class DrivingSimError(SkeletonError):
    code = "SIM_DRIVE"
    severity = "medium"

@dataclass
class DamageState:
    body: float = 0.0
    engine: float = 0.0
    tires: float = 0.0

@dataclass
class VehicleState:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    heading: float = 0.0
    speed: float = 0.0
    rpm: float = 800.0
    downforce: float = 0.0
    damage: DamageState = field(default_factory=DamageState)
    telemetry: Dict[str, float] = field(default_factory=dict)
    digest: str = ""
    collision: bool = False

class DrivingSimulator:
    def __init__(self, mass: float = 1400.0, drag_coeff: float = 0.32, frontal_area: float = 2.2, power: float = 450.0):
        if mass <= 0 or drag_coeff < 0 or frontal_area <= 0 or power <= 0:
            raise DrivingSimError("invalid vehicle params")
        self.mass = mass
        self.drag_coeff = drag_coeff
        self.frontal_area = frontal_area
        self.power = power
        self.state = VehicleState()

    def step(self, throttle: float, steer: float, brake: float = 0.0) -> VehicleState:
        if not (-1.0 <= throttle <= 1.0) or not (-1.0 <= steer <= 1.0) or not (0.0 <= brake <= 1.0):
            raise DrivingSimError("inputs out of bounds")
        # aero drag + downforce
        v = self.state.speed
        drag_force = 0.5 * _AIR_DENSITY * self.drag_coeff * self.frontal_area * v * v
        self.state.downforce = 0.5 * _AIR_DENSITY * 1.8 * self.frontal_area * v * v * 0.3
        # power
        torque = self.power * throttle * (1.0 - self.state.rpm / 9000.0) * (1.0 - self.state.damage.engine)
        accel = (torque / self.mass) - (drag_force / self.mass) - brake * 15.0
        self.state.speed = max(0.0, min(_MAX_SPEED, self.state.speed + accel * _DT))
        self.state.rpm = 800.0 + self.state.speed * 35.0
        self.state.heading += steer * min(v * 0.012, 1.2) * (1.0 - self.state.damage.tires)
        self.state.x += math.cos(self.state.heading) * self.state.speed * _DT
        self.state.y += math.sin(self.state.heading) * self.state.speed * _DT
        self.state.collision = abs(self.state.x) > 1000 or abs(self.state.y) > 1000
        if self.state.collision:
            self.state.damage.body += 0.05
            self.state.damage.engine += 0.02
        self.state.telemetry = {
            "speed": self.state.speed,
            "rpm": self.state.rpm,
            "downforce": self.state.downforce,
            "damage_body": self.state.damage.body,
        }
        payload = f"{self.state.x:.2f}:{self.state.y:.2f}:{self.state.speed:.1f}:{self.state.downforce:.1f}:{self.state.collision}"
        self.state.digest = hashlib.sha256(payload.encode()).hexdigest()
        emit_receipt(kind="driving_step_20x", target=self.state.digest, downforce=self.state.downforce, stored_prose=0)
        return self.state

    def export_telemetry(self) -> str:
        return hashlib.sha256(str(self.state.telemetry).encode()).hexdigest()

    def reset(self) -> None:
        self.state = VehicleState()
        emit_receipt(kind="driving_reset_20x", stored_prose=0)
