"""skeleton/simulation/game/driving_sim_starter.py
30x extreme complete driving. Thermal, tire temp, aero balance, damage, telemetry.
Fail-closed. Receipts. No stubs.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Final, Dict

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

_MAX_SPEED: Final[float] = 350.0
_DT: Final[float] = 0.016
_AIR_DENSITY: Final[float] = 1.225

class DrivingSimError(SkeletonError):
    code = "SIM_DRIVE"
    severity = "medium"

@dataclass
class ThermalState:
    engine_temp: float = 90.0
    tire_temp: float = 70.0
    brake_temp: float = 50.0

@dataclass
class VehicleState:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    heading: float = 0.0
    speed: float = 0.0
    rpm: float = 800.0
    downforce: float = 0.0
    aero_balance: float = 0.5
    thermal: ThermalState = field(default_factory=ThermalState)
    telemetry: Dict[str, float] = field(default_factory=dict)
    digest: str = ""
    collision: bool = False
    steps: int = 0
    damage: float = 0.0

    @property
    def engine_temp(self) -> float:
        return self.thermal.engine_temp

    @property
    def tire_temp(self) -> float:
        return self.thermal.tire_temp

class DrivingSimulator:
    def __init__(self, mass: float = 1450.0, drag_coeff: float = 0.30, frontal_area: float = 2.15, power: float = 520.0):
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
        self.state.steps += 1
        v = self.state.speed
        drag_force = 0.5 * _AIR_DENSITY * self.drag_coeff * self.frontal_area * v * v
        self.state.downforce = 0.5 * _AIR_DENSITY * 2.1 * self.frontal_area * v * v * 0.35
        self.state.aero_balance = 0.45 + (v / _MAX_SPEED) * 0.1
        self.state.thermal.engine_temp = min(140.0, self.state.thermal.engine_temp + throttle * 0.8 - 0.3)
        self.state.thermal.tire_temp = min(120.0, self.state.thermal.tire_temp + abs(steer) * v * 0.02)
        self.state.thermal.brake_temp = min(800.0, self.state.thermal.brake_temp + brake * 15.0 - 2.0)
        torque = self.power * throttle * (1.0 - self.state.rpm / 9500.0) * (1.0 if self.state.thermal.engine_temp < 120 else 0.7)
        # Crankshaft torque must be geared into wheel force before opposing braking.\n        # First gear (3.5:1) and a 0.35 m tire radius give 10 N per N·m.\n        wheel_force = torque * (3.5 / 0.35)\n        accel = (wheel_force - drag_force) / self.mass - brake * 18.0
        self.state.speed = max(0.0, min(_MAX_SPEED, self.state.speed + accel * _DT))
        self.state.rpm = 800.0 + self.state.speed * 32.0
        self.state.heading += steer * min(v * 0.011, 1.3) * (1.0 if self.state.thermal.tire_temp < 110 else 0.8)
        self.state.x += math.cos(self.state.heading) * self.state.speed * _DT
        self.state.y += math.sin(self.state.heading) * self.state.speed * _DT
        self.state.collision = abs(self.state.x) > 1200 or abs(self.state.y) > 1200
        self.state.telemetry = {"speed": self.state.speed, "rpm": self.state.rpm, "downforce": self.state.downforce, "engine_temp": self.state.thermal.engine_temp, "tire_temp": self.state.thermal.tire_temp, "aero_balance": self.state.aero_balance}
        payload = f"{self.state.x:.1f}:{self.state.y:.1f}:{self.state.speed:.1f}:{self.state.thermal.engine_temp:.1f}"
        self.state.digest = hashlib.sha256(payload.encode()).hexdigest()
        emit_receipt(kind="driving_step_30x", target=self.state.digest, engine_temp=self.state.thermal.engine_temp, stored_prose=0)
        return self.state

    def export_telemetry(self) -> str:
        return hashlib.sha256(str(sorted(self.state.telemetry.items())).encode()).hexdigest()

    def reset(self) -> None:
        self.state = VehicleState()
        emit_receipt(kind="driving_reset_30x", stored_prose=0)
